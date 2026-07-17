# Cloudflare Worker Edge Integration Guide

This document describes the deployment, configuration, and integration of the AgentGuard Cloudflare Worker Edge Gateway.

---

## Architecture Overview

```
Developer / Client
       |
       v  (HTTPS)
  Cloudflare Worker Edge  <---->  GitHub (Webhooks)
       |
       v  (Proxied Request / TLS Origin)
  FastAPI Backend (Origin Server)
```

The Worker edge layer sits in front of the FastAPI backend. It serves three roles:
1. **API Gateway & Routing**: Proxies all requests to `/v1/*` to the FastAPI backend, while serving local health checks.
2. **Edge Authentication check**: Automatically rejects requests missing an `Authorization` header starting with `Bearer ag_` directly at the edge, reducing origin load.
3. **GitHub Webhook Automator**: Signature-verifies `POST /webhooks/github` webhooks, fetches the current `manifest.json` from GitHub, registers the version, and triggers the deployment check dynamically.

---

## Local Setup & Wrangler

1. Navigate to the `edge-worker` directory:
   ```bash
   cd edge-worker
   ```

2. Install Wrangler locally:
   ```bash
   npm install
   ```

3. Run Wrangler dev server locally:
   ```bash
   npm run dev
   ```
   By default, this launches the worker local listener at `http://localhost:8787`.

---

## Configuration Variables

Configure these settings in `wrangler.toml` (vars) or via secrets:

| Variable Name | Scope / Type | Description |
|---|---|---|
| `BACKEND_URL` | Variable | The root URL of the FastAPI backend (default: `http://localhost:8000`). |
| `GITHUB_WEBHOOK_SECRET` | Secret | The secret used to HMAC-SHA256 verify incoming GitHub webhooks. |
| `GITHUB_TOKEN` | Secret | A GitHub Personal Access Token (PAT) used to fetch `manifest.json` from private repositories. |
| `AGENTGUARD_API_KEY` | Secret | An AgentGuard API key with `write` and `scan` scopes used to interact with the backend APIs. |

### Adding Secrets in Production:
```bash
npx wrangler secret put GITHUB_WEBHOOK_SECRET
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put AGENTGUARD_API_KEY
```

---

## GitHub Webhook Integration

To automate scans on every pull request/push:

1. Go to your GitHub Repository -> **Settings** -> **Webhooks** -> **Add Webhook**.
2. Configure settings:
   - **Payload URL**: `https://<your-worker-domain>.workers.dev/webhooks/github`
   - **Content type**: `application/json`
   - **Secret**: Enter the exact secret string matching `GITHUB_WEBHOOK_SECRET`.
   - **Which events**: Select **Let me select individual events** and check **Pushes** and **Pull requests**.
3. Click **Add Webhook**.

---

## Backend Origin Security

To ensure clients cannot bypass the Cloudflare Gateway and hit the backend directly, implement these origin security practices:

1. **IP Whitelisting**: Restrict backend inbound network access to Cloudflare's published IP ranges.
2. **Origin Header Token (Tunneling)**: Configure a shared secret header (e.g. `X-Origin-Token`). The Worker injects it, and FastAPI's middleware validates it, rejecting requests missing the token.
