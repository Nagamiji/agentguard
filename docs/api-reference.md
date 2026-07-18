# API Reference

Base URL: `https://api.agentguard.dev`

All endpoints require `Authorization: Bearer {api_key}` unless noted.

All error responses follow the [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457) format with an additional `error` envelope:

```json
{
  "type": "about:blank",
  "title": "Human-readable description",
  "status": 401,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or revoked API key",
    "request_id": "abc123"
  }
}
```

---

## Health

### `GET /healthz` · `GET /health`

Liveness check. No auth required.

**Response 200:**
```json
{"status": "ok", "version": "0.0.1"}
```

### `GET /readyz` · `GET /ready`

Readiness check. Returns 503 if Postgres or Redis are unavailable.

**Response 200:**
```json
{
  "status": "ready",
  "checks": {"database": true, "redis": true}
}
```

### `GET /metrics`

Prometheus-format metrics exposition.

### `GET /v1/version`

**Response 200:**
```json
{"version": "0.0.1", "environment": "production"}
```

---

## Onboarding

### `POST /v1/onboarding` *(no auth)*

Create an organization and issue its first API key.

**Body:**
```json
{"organization_name": "Acme Support AI"}
```

**Response 201:**
```json
{
  "organization_id": "uuid",
  "api_key": "ag_xxxx",
  "next_steps": "..."
}
```

---

## Organizations

### `POST /v1/orgs` *(no auth)*

Bootstrap an org (legacy endpoint — prefer `/v1/onboarding`).

### `POST /v1/orgs/keys`

Issue a scoped API key for the authenticated org.

**Body:**
```json
{"name": "ci-key", "scopes": ["scan", "read"]}
```

### `GET /v1/orgs/keys`

List all API keys for the authenticated org. Never returns plaintext key values.

### `DELETE /v1/orgs/keys/{key_id}`

Revoke an API key immediately.

---

## Admin

*Requires `admin` scope.*

### `POST /v1/admin/orgs/{id}/activate`

Transition an org from `pending` or `suspended` → `active`.

### `POST /v1/admin/orgs/{id}/suspend`

Suspend an org — all authentication is rejected until reactivated.

---

## Agents

### `POST /v1/agents`

Register an AI agent.

**Body:**
```json
{"name": "Support Bot", "slug": "support-bot"}
```

### `GET /v1/agents`

List all agents for the authenticated org.

### `GET /v1/agents/{id}`

Fetch a specific agent by ID.

### `PATCH /v1/agents/{id}`

Update agent name or metadata.

---

## Manifests & Versions

### `POST /v1/agents/{id}/versions`

Upload a new agent manifest version.

### `GET /v1/agents/{id}/versions`

List all versions for an agent.

---

## Scans / Evaluation Runs

### `POST /v1/runs`

Execute a security evaluation scan.

**Body:**
```json
{
  "agent_id": "uuid",
  "version_id": "uuid",
  "environment": "prod",
  "runner": "scripted"
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "gate_decision": "BLOCKED",
  "status": "complete",
  "failed_scenarios": 2,
  "total_scenarios": 5
}
```

---

## Policies

### `POST /v1/policies`

Create a policy for an org.

### `GET /v1/policies`

List active policies for the authenticated org.

---

## Error Codes Reference

| Code | HTTP | Meaning |
|:-----|:-----|:--------|
| `UNAUTHORIZED` | 401 | Auth header missing, malformed, or key invalid |
| `FORBIDDEN` | 403 | Key valid but insufficient scope, or org suspended |
| `NOT_FOUND` | 404 | Resource does not exist in this org's scope |
| `CONFLICT` | 409 | Slug already registered |
| `PAYMENT_REQUIRED` | 402 | Plan limit reached — upgrade required |
| `VALIDATION_ERROR` | 422 | Request body failed schema validation |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests — back off and retry |
| `INTERNAL_ERROR` | 500 | Unexpected server error |
| `SERVICE_UNAVAILABLE` | 503 | Dependency (DB/Redis) unreachable |
