# agent-reliability-platform (AgentGuard / Keel)

The reliability & deployment-gate platform for AI agents — control plane + workers. This is the **product repo**; company governance, architecture, and the 90-day plan live in the **Keel OS repo** (`../keel`, see `CLAUDE.md`).

Status: **`DO-01` scaffold** — a runnable FastAPI app + worker + local stack + CI. This is loop iteration #1; the reliability pipeline gets built on top (`../keel/execution/backlog/`).

## Quickstart
```bash
make install     # venv + dev deps (Python 3.12+)
make up          # start Postgres(pgvector) + Redis via docker compose
cp .env.example .env
make dev         # run the API → http://localhost:8000/healthz
make check       # lint + typecheck + test (what CI runs)
```

## Layout
```
src/keel/        FastAPI app: config, logging, errors (RFC-9457), tenant middleware, /healthz /readyz
src/worker/      Redis-stream worker skeleton (idempotent)
tests/           pytest (health + error contract)
infrastructure/  Terraform skeleton ([NOW] modules only — governed by ../keel/infrastructure)
.github/         CI: ruff + mypy + pytest + gitleaks
```

## Principles (from the OS — `CLAUDE.md`)
Boring/proven stack · reproducibility + tenant isolation from day one · no secrets in code · maker≠checker + human gate on every merge · no manual cloud changes (IaC only).
