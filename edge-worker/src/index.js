export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. Health check endpoint (handled directly at the edge)
    if (url.pathname === "/healthz") {
      return new Response(JSON.stringify({ status: "ok", gateway: "cloudflare-edge" }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }

    // 2. GitHub Webhook endpoint
    if (url.pathname === "/webhooks/github") {
      return handleGithubWebhook(request, env);
    }

    // 3. API gateway proxy routing (/v1/*)
    if (url.pathname.startsWith("/v1/")) {
      return handleApiProxy(request, env);
    }

    // Default route
    return new Response(JSON.stringify({ error: "Not Found", code: 404 }), {
      status: 404,
      headers: { "Content-Type": "application/json" }
    });
  }
};

/**
 * Validates API Key scopes format and proxies requests to the FastAPI backend.
 */
async function handleApiProxy(request, env) {
  const authHeader = request.headers.get("Authorization");

  // Edge Gateway Authentication: Check key format before proxying
  if (!authHeader || !authHeader.startsWith("Bearer ag_")) {
    return new Response(
      JSON.stringify({
        type: "about:blank",
        title: "Unauthorized: Missing or invalid API key format",
        status: 401,
        instance: new URL(request.url).pathname
      }),
      {
        status: 401,
        headers: { "Content-Type": "application/problem+json" }
      }
    );
  }

  // Build target URL
  const backendBase = env.BACKEND_URL || "http://localhost:8000";
  const targetUrl = new URL(request.url);
  const proxyUrl = `${backendBase}${targetUrl.pathname}${targetUrl.search}`;

  // Clone headers and inject audit metrics context
  const newHeaders = new Headers(request.headers);
  newHeaders.set("x-request-id", request.headers.get("x-request-id") || crypto.randomUUID());

  const connectingIp = request.headers.get("CF-Connecting-IP");
  if (connectingIp) {
    newHeaders.set("x-forwarded-for", connectingIp);
  }
  const country = request.headers.get("CF-IPCountry");
  if (country) {
    newHeaders.set("x-client-country", country);
  }

  // Forward request body if present
  let body = null;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request.clone().arrayBuffer();
  }

  try {
    const response = await fetch(proxyUrl, {
      method: request.method,
      headers: newHeaders,
      body: body
    });

    // Clone and return response with CORS headers
    const resHeaders = new Headers(response.headers);
    resHeaders.set("Access-Control-Allow-Origin", "*");
    resHeaders.set("Access-Control-Allow-Headers", "Content-Type, Authorization");
    resHeaders.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE");

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: resHeaders
    });
  } catch (e) {
    return new Response(
      JSON.stringify({
        type: "about:blank",
        title: "Gateway Error: Could not connect to backend service",
        status: 502,
        detail: e.message,
        instance: targetUrl.pathname
      }),
      {
        status: 502,
        headers: { "Content-Type": "application/problem+json" }
      }
    );
  }
}

/**
 * Handles GitHub Webhook events and triggers AgentGuard scans.
 */
async function handleGithubWebhook(request, env) {
  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  const signatureHeader = request.headers.get("X-Hub-Signature-256");
  const bodyText = await request.clone().text();

  // Signature check
  const secret = env.GITHUB_WEBHOOK_SECRET;
  if (secret) {
    const isValid = await verifySignature(secret, signatureHeader, bodyText);
    if (!isValid) {
      return new Response("Invalid Signature", { status: 401 });
    }
  }

  const eventType = request.headers.get("X-GitHub-Event");
  let payload;
  try {
    payload = JSON.parse(bodyText);
  } catch (e) {
    return new Response("Invalid JSON Payload", { status: 400 });
  }

  // Handle push or pull_request events
  if (eventType === "push" || eventType === "pull_request") {
    const isPR = eventType === "pull_request";
    const commitSha = isPR ? payload.pull_request.head.sha : payload.after;
    const repoName = payload.repository.name;
    const repoFullName = payload.repository.full_name;

    // Use GITHUB_TOKEN if available, otherwise return 202 indicating basic webhook ack
    const githubToken = env.GITHUB_TOKEN;
    const agentguardKey = env.AGENTGUARD_API_KEY;

    if (!agentguardKey) {
      return new Response(
        JSON.stringify({
          status: "accepted",
          message: "Webhook verified, but AGENTGUARD_API_KEY is not configured on the Worker edge."
        }),
        { status: 202, headers: { "Content-Type": "application/json" } }
      );
    }

    // Run async background processing
    ctx_waitUntil(async () => {
      try {
        const backendBase = env.BACKEND_URL || "http://localhost:8000";

        // 1. Resolve agent by slug (using repoName as slug name)
        const agents = await fetch(`${backendBase}/v1/agents`, {
          headers: { "Authorization": `Bearer ${agentguardKey}` }
        }).then(r => r.json());

        const agent = agents.find(a => a.slug === repoName || a.name === repoName);
        if (!agent) {
          console.error(`Agent not found in registry for slug/repo: ${repoName}`);
          return;
        }

        // 2. Fetch manifest.json from GitHub if GITHUB_TOKEN is present
        let manifest = null;
        if (githubToken) {
          const githubUrl = `https://api.github.com/repos/${repoFullName}/contents/manifest.json?ref=${commitSha}`;
          const ghRes = await fetch(githubUrl, {
            headers: {
              "User-Agent": "AgentGuard-Edge-Gateway",
              "Authorization": `token ${githubToken}`,
              "Accept": "application/vnd.github.v3.raw"
            }
          });
          if (ghRes.ok) {
            manifest = await ghRes.json();
          }
        }

        if (!manifest) {
          console.error(`Could not retrieve manifest.json for SHA ${commitSha} in ${repoFullName}`);
          return;
        }

        // 3. Create version in AgentGuard
        const version = await fetch(`${backendBase}/v1/agents/${agent.id}/versions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${agentguardKey}`
          },
          body: JSON.stringify({ manifest })
        }).then(r => r.json());

        // 4. Trigger scan
        await fetch(`${backendBase}/v1/agents/${agent.id}/runs`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${agentguardKey}`
          },
          body: JSON.stringify({
            version_id: version.id,
            runner: "scripted",
            environment: "prod"
          })
        });

      } catch (e) {
        console.error("Error executing background webhook task:", e);
      }
    });

    return new Response(
      JSON.stringify({
        status: "accepted",
        repo: repoFullName,
        commit: commitSha,
        event: eventType
      }),
      { status: 202, headers: { "Content-Type": "application/json" } }
    );
  }

  return new Response("Event skipped", { status: 200 });
}

/**
 * Standard crypto HMAC-SHA256 signature verifier.
 */
async function verifySignature(secret, header, bodyText) {
  if (!header || !header.startsWith("sha256=")) return false;
  const signature = header.slice(7);

  const encoder = new TextEncoder();
  const secretKeyData = encoder.encode(secret);
  const key = await crypto.subtle.importKey(
    "raw",
    secretKeyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );

  const verified = await crypto.subtle.verify(
    "HMAC",
    key,
    hexToBytes(signature),
    encoder.encode(bodyText)
  );
  return verified;
}

function hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
  }
  return bytes;
}

// Fallback for execution context waitUntil
function ctx_waitUntil(fn) {
  try {
    fn();
  } catch (e) {
    console.error(e);
  }
}
