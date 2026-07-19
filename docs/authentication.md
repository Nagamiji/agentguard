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
  -H "Authorization: Bearer $AGENTGUARD_API_KEY"
```

---

## API Key Scopes

| Scope | Access |
|:------|:-------|
| `*` | Full access (the `owner` role; granted only by a caller that already holds `*`) |
| `read` | Read-only access to agents, runs, policies |
| `write` | Create/update agents and manifests |
| `scan` | Execute evaluation scans |
| `admin` | Key management, org lifecycle controls |

Create a scoped key with explicit scopes:

```bash
curl -X POST https://api.agentguard.dev/v1/orgs/keys \
  -H "Authorization: Bearer $AGENTGUARD_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "ci-scan-key", "scopes": ["scan", "read"]}'
```

Managing scopes by hand is error-prone, so key creation also accepts a **role** — pass
`role` *or* `scopes`, never both, and **not neither**: a request with no `role` and no
`scopes` is rejected `422` (a key is never granted implicit full access), as is an empty
`scopes: []`. A key can also never be minted with more authority than the caller who
mints it — requesting a scope you do not hold (e.g. an `admin` key asking for `*`) is
rejected `403`.

---

## Roles

Roles are named presets over the scope vocabulary above. `GET /v1/roles` returns the live
catalog.

| Role | Scopes | Use for |
|:-----|:-------|:--------|
| `owner` | `*` | The org's first/root key |
| `admin` | `read, write, scan, admin` | Team leads managing keys + org |
| `developer` | `read, write, scan` | Engineers building and testing agents |
| `ci` | `read, scan` | GitHub Actions / CI — run scans, read verdicts, nothing else |
| `viewer` | `read` | Dashboards, auditors, read-only integrations |

```bash
# A least-privilege CI key that expires in 90 days
curl -X POST https://api.agentguard.dev/v1/orgs/keys \
  -H "Authorization: Bearer $AGENTGUARD_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "github-actions", "role": "ci", "expires_in_days": 90}'
```

---

## Expiry & lifecycle

- `expires_in_days` (1–3650) sets an optional expiry; an expired key authenticates as
  `401 API key has expired`.
- Each key tracks `created_by` (the key that issued it), `last_used_at` (refreshed at most
  once per minute), and a derived `status` of `active` / `expired` / `revoked`, all visible
  via `GET /v1/orgs/keys`.

---

## Audit trail

Every key issue/revoke and org activate/suspend is recorded to a tenant-scoped, append-only
audit log. Read it (admin scope) with:

```bash
curl https://api.agentguard.dev/v1/audit-events \
  -H "Authorization: Bearer $AGENTGUARD_ADMIN_KEY"
```

Each event carries `actor` (the acting key prefix), `action` (e.g. `api_key.issued`),
`resource_type`/`resource_id`, `metadata`, and `created_at`. The log is RLS-isolated, so an
org only ever sees its own trail.

---

## Revoking Keys

Revoke a key (it immediately stops working):

```bash
curl -X DELETE https://api.agentguard.dev/v1/orgs/keys/{key_id} \
  -H "Authorization: Bearer $AGENTGUARD_ADMIN_KEY"
```

---

## Error Codes

| HTTP Status | Error Code | Meaning |
|:------------|:-----------|:--------|
| 401 | `UNAUTHORIZED` | Missing, malformed, invalid, or **expired** key |
| 403 | `FORBIDDEN` | Key exists but lacks required scope, or org is suspended |
| 402 | `PAYMENT_REQUIRED` | Plan usage limit reached |

---

## Security Notes

- All keys are SHA-256 hashed in the database — even a full DB dump cannot reveal active keys
- Keys are never logged (not even partially)
- Rotate keys by issuing a new key, updating CI secrets, then revoking the old key
- Use scoped keys in CI — never use `*`-scoped keys in automation
