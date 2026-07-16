# Development Guide

Goal: a new contributor gets to a running local stack in **under a day** (the `DO-01` / `ARCH-05` DoD).

## Prerequisites
- Python 3.12+ · Docker + Docker Compose · Make

## Run it
```bash
make install          # venv + dev deps
make up               # Postgres(pgvector) + Redis
cp .env.example .env
make dev              # API → http://localhost:8000
curl localhost:8000/healthz   # {"status":"ok","version":"0.0.1"}
curl localhost:8000/readyz    # 200 when DB up, 503 when down
make worker           # in another shell: starts the Redis-stream worker
```

## Quality gates (run before every PR)
```bash
make check            # ruff (lint) + mypy (types, strict) + pytest
```
CI runs the same three + gitleaks secret scan on every PR. **Nothing merges to `main` without an independent review (maker≠checker) + human approval** (`../../keel/loops/`).

## Project shape
| Path | Purpose |
|---|---|
| `src/keel/config.py` | Settings via `KEEL_*` env vars (no hardcoded secrets) |
| `src/keel/main.py` | App factory: middleware + error handlers + routers |
| `src/keel/errors.py` | RFC-9457 Problem Details |
| `src/keel/middleware.py` | request-id + tenant context (real auth = `BE-01`) |
| `src/keel/db.py` | SQLAlchemy engine/session + readiness check |
| `src/keel/api/` | Routers (`health.py` now; registry/eval/gate next) |
| `src/worker/` | Redis-stream worker (idempotent) |
| `infrastructure/terraform/` | IaC skeleton (live modules at `PLAT-01`) |

## Adding an endpoint
1. New router in `src/keel/api/<name>.py`; include it in `main.py`.
2. Pydantic models at the boundary; RFC-9457 errors; tenant-scope every query (RLS lands with `BE-01`/`SEC-02`).
3. Tests in `tests/`; `make check`; open PR → checker → human gate.

## What to build next
`../../keel/execution/backlog/` — `BE-01` (projects+auth+org isolation) is the next critical-path task.
