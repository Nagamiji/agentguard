# Self-Serve Customer Onboarding Guide

Welcome to AgentGuard! This guide outlines how to onboard your team, set up your credentials, and run your first agent security check in minutes.

---

## Step 1: Create an Account & API Key

Register your organization and receive your initial API key via a single API call to the onboarding endpoint:

```bash
curl -X POST https://api.agentguard.security/v1/onboarding \
  -H "Content-Type: application/json" \
  -d '{"organization_name": "Acme Corp"}'
```

### Response:
```json
{
  "organization_id": "4a7b7e80-d66a-4ee1-bcf3-a74e2d31dc0b",
  "api_key": "ag_7a1Fh8_3b9K9...[SHOWN ONCE]",
  "next_steps": "Welcome to AgentGuard! To integrate security scans into your workflow..."
}
```

> [!IMPORTANT]
> **Your API key is only shown once.** AgentGuard stores only cryptographic SHA-256 hashes of API keys to protect against credential leaks, meaning lost keys cannot be recovered.

---

## Step 2: Configure CLI and Local Environment

1. Install the CLI client:
   ```bash
   pip install agentguard-cli
   ```

2. Export the credential token to your shell or CI runner context:
   ```bash
   export AGENTGUARD_API_KEY="ag_..."
   ```

3. Initialize your configuration manifest within your codebase root:
   ```bash
   agentguard init
   ```
   This creates a `manifest.json` describing your agent's system prompt, active tools, and LLM model selections.

---

## Step 3: Run Your First Scan

Execute the validation gate locally or in your CI workflow:

```bash
agentguard scan --agent-slug customer-support
```
This triggers an automated evaluation run checking your agent configuration against policy constraints and active vulnerability libraries.
