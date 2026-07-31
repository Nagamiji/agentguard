# Troubleshooting

Common issues and diagnostic steps for AgentGuard operators and developers.

---

## API Container Exits Immediately on Startup

**Symptom**: `docker compose up` shows the api container as `Exited (1)`.

**Check logs first:**
```bash
docker compose logs api
```

**Common causes:**

1. **Missing production secrets** — if `KEEL_APP_ENV=production` and `KEEL_SECRET_KEY` or `KEEL_API_KEY_HASH_SECRET` are not set, the server refuses to start with:
   ```
   RuntimeError: Missing critical production configurations: KEEL_SECRET_KEY
   ```
   Fix: set the required env vars.

2. **Database not reachable** — ensure Postgres is healthy before the API starts.
   ```bash
   docker compose ps
   ```
   Check the `postgres` service shows `healthy`.

3. **Migrations not applied** — the API does not auto-migrate; run migrations before starting:
   ```bash
   alembic upgrade head
   ```

---

## `401 Unauthorized` on Valid Key

- Verify the full key is being sent (starts with `ag_`)
- Verify the key has not been revoked (`GET /v1/orgs/keys` to list active keys)
- Check the org is not `suspended` (`/v1/admin/orgs/{id}`)
- Verify `Authorization: Bearer {key}` format (not just the key value)

---

## `403 Forbidden` on Valid Key

- The key may lack the required scope for that endpoint
- The organization may be `suspended`

Check:
```bash
curl -H "Authorization: Bearer $KEY" https://api.agentguard.dev/v1/orgs/keys
```

Look at the `scopes` field on your key.

---

## `402 Payment Required` on Scans or Agent Registration

Your organization has reached its plan limit:

- **Free plan**: 1 agent, 10 scans
- **Pilot plan**: 5 agents, 100 scans
- **Enterprise**: unlimited

Contact support to upgrade or request a limit increase.

---

## `503 Service Unavailable` from `/readyz`

The API is running but cannot reach a dependency:

```bash
curl https://api.agentguard.dev/readyz
```

```json
{"status": "degraded", "checks": {"database": false, "redis": true}}
```

Check that Postgres and Redis are running and accessible from the API container.

---

## Migrations Fail

```bash
alembic upgrade head
# Error: relation "plans" does not exist
```

Possible causes:
- Running migration as the wrong role (must be the owner `keel` role, not `keel_app`)
- Partial migration state — check `alembic current` and `alembic history`

---

## Rate Limit Errors (`429 Too Many Requests`)

AgentGuard rate-limits by organization:
- **General endpoints**: 100 req/min
- **Scans**: 10 scans/min

Back off exponentially and retry.

---

## Viewing Logs

Structured JSON logs are emitted to stdout. Fields include:

| Field | Description |
|:------|:------------|
| `level` | Log level (INFO, ERROR, etc.) |
| `message` | Human-readable message |
| `request_id` | Request correlation ID |
| `org_id` | Authenticated organization ID |
| `run_id` | Evaluation run ID (if applicable) |

Filter by request ID:
```bash
docker compose logs api | jq 'select(.request_id == "abc123")'
```
