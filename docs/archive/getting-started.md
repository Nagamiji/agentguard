# Getting Started with AgentGuard

AgentGuard is a security and reliability gate for AI agents — similar to Snyk for code, but for AI agent behavior, tool calls, and policy violations.

## Prerequisites

- Python 3.12+
- Docker + Docker Compose (for local stack)
- An AgentGuard account and API key

---

## Step 1 — Create Your Account

Send a `POST /v1/onboarding` request to provision your organization and get your first API key:

```bash
curl -X POST https://api.agentguard.dev/v1/onboarding \
  -H "Content-Type: application/json" \
  -d '{"organization_name": "Acme Support AI"}'
```

Response:

```json
{
  "organization_id": "d781b2a9-...",
  "api_key": "ag_live_xxxxxxxx",
  "next_steps": "Welcome to AgentGuard! ..."
}
```

> **Important**: Your API key is shown **once**. Store it in your secrets manager immediately.

---

## Step 2 — Export Your Credentials

```bash
export AGENTGUARD_API_KEY="ag_live_xxxxxxxx"
export AGENTGUARD_API_URL="https://api.agentguard.dev"
```

---

## Step 3 — Install the AgentGuard CLI

```bash
pip install agentguard-cli
```

Verify:

```bash
agentguard --version
```

---

## Step 4 — Register Your First Agent

```bash
agentguard agent create \
  --api-url "$AGENTGUARD_API_URL" \
  --name "customer-support-bot" \
  --slug "support-bot"
```

---

## Step 5 — Write a Manifest

Create `agent-manifest.json`:

```json
{
  "prompts": [
    {"role": "system", "content": "You are a helpful support agent."}
  ],
  "tools": [
    {
      "name": "issue_refund",
      "description": "Refund a customer order",
      "schema": {
        "type": "object",
        "properties": {"amount": {"type": "number"}}
      }
    }
  ],
  "model": {"provider": "vertex", "id": "gemini-2.5-flash"},
  "params": {"temperature": 0}
}
```

---

## Step 6 — Run Your First Scan

```bash
agentguard scan \
  --api-url "$AGENTGUARD_API_URL" \
  --agent "support-bot" \
  --manifest agent-manifest.json \
  --environment prod
```

You will receive a gate decision: `ALLOWED` or `BLOCKED`.

---

## Step 7 — Add to CI/CD

Add to your `.github/workflows/ci.yml`:

```yaml
- name: AgentGuard Security Scan
  run: |
    agentguard scan \
      --api-url ${{ vars.AGENTGUARD_API_URL }} \
      --agent your-agent-slug \
      --manifest agent-manifest.json \
      --environment prod
  env:
    AGENTGUARD_API_KEY: ${{ secrets.AGENTGUARD_API_KEY }}
```

---

## Next Steps

- Read the [API Reference](api-reference.md) for endpoint details
- Review [Authentication](authentication.md) for key management
- See [Deployment](deployment.md) for self-hosted setup
