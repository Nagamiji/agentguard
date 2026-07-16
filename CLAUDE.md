# CLAUDE.md — product repo

This is the **AgentGuard / Keel platform** code. The company operating system — vision, architecture, decisions, 90-day plan, standards, loops — lives in the **Keel OS repo** at `../keel`. **Read `../keel/CLAUDE.md` first**, then this.

## What this repo is
The control plane + workers for the AI agent reliability platform. Currently the `DO-01` scaffold.

## Prime directive
Ship toward the one goal: *a developer can connect an agent → run reliability tests in CI → get a failure report → block the deploy.* Grade every change against it (`../keel/execution/90-day-plan.md`).

## Rules (inherited — `../keel/CLAUDE.md`)
- **Maker ≠ Checker; human gate on every merge.** Nothing auto-merges to `main`.
- **No secrets in code.** Config via `KEEL_*` env vars (`src/keel/config.py`), secrets via a manager in cloud.
- **Tenant isolation + reproducibility are day-one**, not later.
- **Infrastructure is code** — no manual cloud changes (`../keel/os/standards/infrastructure.md`).
- **Boring, proven tech**; deviations need a TDR in the OS repo.
- Stack: Python/FastAPI · Postgres+pgvector · Redis(→Kafka) · ClickHouse(later) · R2 · LiteLLM · OTel.

## Conventions
- Errors: RFC-9457 Problem Details (`src/keel/errors.py`).
- Every request gets a request-id + tenant context (`src/keel/middleware.py`).
- Tests via `pytest` (pythonpath=src); lint `ruff`; types `mypy --strict`.
- Run `make check` before opening a PR.

## Where to build next
The `[NOW]` backlog tasks (`../keel/execution/backlog/`): `BE-01` projects+auth+org isolation, `BE-02` agent registry, `AI-01` trace SDK, `EVAL-01` eval pipeline. One task per loop iteration.
