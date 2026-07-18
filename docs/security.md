# Security

This document describes AgentGuard's security model and the protections in place for beta customers.

---

## Authentication

- **API keys** are 128-bit random values, prefixed `ag_` for detectability
- Keys are **SHA-256 hashed** (HMAC) before storage — the database never contains plaintext keys
- Even a full database dump cannot be used to forge requests
- Revoked keys stop working immediately at the next request

## Authorization

- All tenant data access is protected by **PostgreSQL Row-Level Security (RLS)**
- The API connects as the `keel_app` role — a non-superuser that RLS always applies to
- Tenant context (`app.current_org_id`) is set per database transaction using `SET LOCAL`, scoped to that transaction only — not a persistent session variable
- Cross-tenant data access is impossible by design: RLS filters every `SELECT`, `INSERT`, `UPDATE`, and `DELETE`

## Organization Lifecycle

- Suspended organizations are rejected at the authentication layer (403) before any DB query runs for business logic
- Deleted organizations retain their data for audit trail purposes

## Secret Handling

- No secrets are stored in environment variables at build time
- Secrets arrive at runtime via `KEEL_*` environment variables
- The application refuses to start in `production` mode if critical secrets are absent
- Secrets are never logged, even partially — `ContextFilter` explicitly excludes them
- All pre-commit hooks include `gitleaks` secret scanning

## Transport Security

- All public endpoints are served over HTTPS via the Cloudflare edge layer
- Security headers are set at the Cloudflare Worker layer: `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`

## Dependency Security

- **pip-audit** runs on every PR to detect known CVEs in dependencies
- **Trivy** scans the container image for OS and library vulnerabilities on every PR
- **gitleaks** scans the full git history for accidentally committed secrets

## Rate Limiting

- General API: 100 requests/min per organization
- Scan execution: 10 scans/min per organization
- Rate limit state is stored in Redis with TTL-based sliding windows
- Exceeding limits returns `429 Too Many Requests` with `Retry-After` header

## Incident Reporting

If you discover a security issue, contact security@agentguard.dev. Do not open a public GitHub issue.

---

## Compliance Notes (Beta)

- Data is not end-to-end encrypted at rest yet — full encryption at rest is planned before GA
- RLS policies cover: `agents`, `agent_versions`, `agent_aliases`, `eval_runs`, `eval_results`, `api_keys`, `usage_events`
- Audit logging captures all scan decisions with timestamps and organization context
