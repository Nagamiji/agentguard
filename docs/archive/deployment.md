# Deployment

This guide covers deploying AgentGuard in production.

---

## Architecture Overview

```
Developer / CI
     │
     ▼
AgentGuard CLI / API Client
     │
     ▼
Cloudflare Worker (Edge Gateway)
     │   ← Security headers, routing, edge caching
     ▼
FastAPI Control Plane (uvicorn)
     │
     ├── PostgreSQL (pgvector, RLS-enforced)
     └── Redis (rate limiting, caching)
```

---

## Local Development Stack

```bash
# Start Postgres + Redis
make up

# Apply migrations
make migrate

# Run the API
make dev
```

---

## Containerised Demo (Docker Compose)

```bash
make demo-cloud
```

This starts a fully isolated stack (no host port conflicts) and runs a complete customer simulation, verifying the BLOCKED decision end-to-end.

---

## Production Deployment

### Required Environment Variables

Copy `.env.example` and configure:

```bash
cp .env.example .env.production
```

Critical required variables:

| Variable | Description |
|:---------|:------------|
| `KEEL_APP_ENV` | Set to `production` |
| `KEEL_SECRET_KEY` | Min 32-char random string |
| `KEEL_API_KEY_HASH_SECRET` | HMAC secret for key hashing |
| `KEEL_DATABASE_URL` | `postgresql+psycopg://keel_app:...@host/keel` |
| `KEEL_MIGRATION_DATABASE_URL` | Owner-role DB URL for schema migrations |
| `KEEL_REDIS_URL` | `redis://...` |

> **Note**: The API refuses to start in `production` mode if `KEEL_SECRET_KEY` or `KEEL_API_KEY_HASH_SECRET` are missing.

### Run Migrations Before Starting

```bash
KEEL_MIGRATION_DATABASE_URL=... alembic upgrade head
```

### Docker

```bash
# Build the image
docker build -t agentguard:latest .

# Start
docker run \
  -e KEEL_APP_ENV=production \
  -e KEEL_DATABASE_URL=... \
  -e KEEL_REDIS_URL=... \
  -e KEEL_SECRET_KEY=... \
  -e KEEL_API_KEY_HASH_SECRET=... \
  -p 8000:8000 \
  agentguard:latest
```

---

## Database Setup

### Create the Least-Privilege App Role

The API connects as `keel_app` (non-superuser, RLS applies). Run once after DB creation:

```sql
CREATE ROLE keel_app LOGIN PASSWORD 'strong-password-here';
GRANT USAGE ON SCHEMA public TO keel_app;
```

In production, this role and password should be managed by Terraform + Secrets Manager.

---

## Cloudflare Worker (Edge Layer)

The Cloudflare Worker acts as a secure proxy. Configure it with the `BACKEND_URL` environment variable pointing to the control plane:

```bash
cd cloudflare-edge
wrangler secret put BACKEND_URL
wrangler deploy
```

---

## Health Checks

Configure your load balancer to use:

- **Liveness**: `GET /healthz` → 200 = process up
- **Readiness**: `GET /readyz` → 200 = DB + Redis reachable, 503 = degraded

---

## Observability

- **Logs**: Structured JSON to stdout — ship to any log aggregator
- **Metrics**: `GET /metrics` returns Prometheus-format exposition
- **Traces**: `X-Request-ID` propagated through all responses for correlation
