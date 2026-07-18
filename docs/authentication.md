# Authentication

AgentGuard uses **Bearer token authentication** with scoped API keys.

---

## API Key Format

All API keys follow the format:

```
ag_{32-hex-character-random-value}
```

Example:

```
ag_f1e2d3c4b5a6978f1e2d3c4b5a6978fe
```

Keys are **SHA-256 hashed** before being stored in the database. The plaintext key is shown exactly once at creation time and cannot be retrieved later.

---

## Authenticating Requests

Pass your API key in the `Authorization` header:

```bash
curl https://api.agentguard.dev/v1/agents \
  -H "Authorization: Bearer ag_your_key_here"
```

---

## API Key Scopes

| Scope | Access |
|:------|:-------|
| `*` | Full access (default for onboarding key) |
| `read` | Read-only access to agents, runs, policies |
| `write` | Create/update agents and manifests |
| `scan` | Execute evaluation scans |
| `admin` | Key management, org lifecycle controls |

Create a scoped key:

```bash
curl -X POST https://api.agentguard.dev/v1/orgs/keys \
  -H "Authorization: Bearer ag_admin_key" \
  -H "Content-Type: application/json" \
  -d '{"name": "ci-scan-key", "scopes": ["scan", "read"]}'
```

---

## Revoking Keys

Revoke a key (it immediately stops working):

```bash
curl -X DELETE https://api.agentguard.dev/v1/orgs/keys/{key_id} \
  -H "Authorization: Bearer ag_admin_key"
```

---

## Error Codes

| HTTP Status | Error Code | Meaning |
|:------------|:-----------|:--------|
| 401 | `UNAUTHORIZED` | Missing, malformed, or invalid key |
| 403 | `FORBIDDEN` | Key exists but lacks required scope, or org is suspended |
| 402 | `PAYMENT_REQUIRED` | Plan usage limit reached |

---

## Security Notes

- All keys are SHA-256 hashed in the database — even a full DB dump cannot reveal active keys
- Keys are never logged (not even partially)
- Rotate keys by issuing a new key, updating CI secrets, then revoking the old key
- Use scoped keys in CI — never use `*`-scoped keys in automation
