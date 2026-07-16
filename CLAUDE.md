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

## Git workflow
- **`main` is protected and always releasable.** It only ever changes via a squash-merged PR.
- **Branch for every change**: `feature/*` (also `fix/*`, `chore/*` — same rules). Never commit to `main` directly.
- **Conventional Commits**: `<type>[(scope)][!]: <subject>` — types `feat fix docs style refactor perf test build ci chore revert`, `!` = breaking.
  - The **PR title is enforced** (`.github/scripts/check-conventional-commits.sh`) because squash-merge lands it on `main` verbatim.
  - Branch commit subjects are **advisory only** — the squash discards them. `make hooks` installs a local `commit-msg` hook that nudges you to the format anyway.
  - The backlog ID is the natural **scope**, which keeps the old `BE-01:` style and this one in one grammar: `feat(be-02): add agent registry endpoint`.
- Rebase on `main` rather than merging it back in; history stays linear.

## CI/CD rules
- `.github/workflows/ci.yml` — the PR gate. One required check, **`gate`**, fans in on:
  ruff · mypy --strict · unit pytest · integration pytest (Postgres + RLS) · gitleaks + pip-audit · Docker build · terraform fmt/validate · commit style.
  Adding a CI job needs no branch-protection change — wire it into `gate`'s `needs`.
- `.github/workflows/security.yml` — weekly (+ manual) gitleaks, pip-audit, Trivy image scan. Catches CVEs filed *after* merge.
- `.github/workflows/release.yml` — fires on `workflow_run` after CI passes on `main`; builds the image and uploads a versioned artifact + manifest (commit sha, digest). Nothing is published to a registry and **nothing deploys itself**.
- Locally, `make check` runs the same lint/typecheck/test trio the gate does.

## Merge requirements
> **⚠️ Not yet enforced.** Branch protection needs GitHub Pro on a private repo (403 as of
> 2026-07-16), so CI **reports** but cannot **block**. Treat the rules below as binding on
> yourself until the platform enforces them — and don't read a green check as a locked
> door. `make hooks` installs a local pre-push guard against direct pushes to `main`, but
> it is bypassable and machine-local, and it cannot stop a web-UI merge.
> See `docs/branch-protection.md`.

Once protection is live, a PR merges only when **all** hold:
1. `gate` is green.
2. The branch is up to date with `main` (strict mode).
3. One approving review — from a code owner for security-critical paths (`.github/CODEOWNERS`).
4. Review conversations are resolved.

**Green CI unlocks the merge button; a human still presses it.** Auto-merge is off at the
repo level, on purpose: CI proves the gates pass, not that the change was correct or
wanted. With Claude as maker, the reviewing human is the only checker — this is the
maker≠checker rule in mechanism form, not just in prose. Turning auto-merge on is a policy
change that must edit this file first.

Caveat, written down rather than hidden: `enforce_admins` is currently **off**, because a
lone maintainer cannot approve their own PR and would otherwise be locked out of `main`.
Claude-authored PRs still get a real second pair of eyes; self-authored ones do not.
Flip it (`ENFORCE_ADMINS=true bash scripts/apply-branch-protection.sh`) once a second
reviewer exists. Details + rationale: `docs/branch-protection.md`.

## Release process
1. PR merges to `main` → CI runs on `main`.
2. Green → `release.yml` builds the artifact **for the exact commit CI validated** and uploads `keel-platform-<version>-<sha>` (image tarball + `manifest.json` + checksum, 30-day retention).
3. Version comes from `pyproject.toml`; bump it in a normal PR.
4. **Deployment is a separate, human-initiated step.** No pipeline touches an environment — infrastructure changes go through Terraform (`../keel/os/standards/infrastructure.md`), never the console.

## Evaluation (EVAL-01/02 — the product)
- **Simulate, never execute** (`docs/architecture/adr-0008-evaluation-engine.md`). A manifest holds tool *schemas*; the implementations are the customer's. Running them to check safety would cause the failure we exist to prevent. `LiveAgentRunner` has no execution path at all — the absence is the safety property, and a test asserts it.
- **The tool call is the unit of judgement, not the prose.** "Certainly! I've processed the $9000 refund" is fluent and helpful-sounding; a text scorer rates it highly. The danger is entirely in the action.
- **Checks are deterministic assertions, never LLM-as-judge.** A blocked deploy must be reproducible and explainable to the engineer it blocked at 2am.
- **Fail closed everywhere.** Unevaluated -> `unknown`; zero scenarios -> `errored`; provider/runner failure -> `errored`. "We could not tell" must never render as "it's fine".
- **Verdicts key on fingerprint**, so a pass belongs to an exact configuration and v2 cannot inherit v1's verdict.
- **Real model access via ADC, never an API key in config** (`adr-0009`). `RUN_VERTEX_EVAL=true make eval-live` runs against live Vertex — costs money, non-deterministic, deliberately outside CI.

## Where to build next
Validated 2026-07-16: a real `gemini-2.5-flash` obeyed a prompt injection and attempted a $9,000 refund; AgentGuard blocked it with evidence and executed nothing.
Next: **Phase 3 — failure scenario library.** Detection is only as good as the scenarios; a customer will not write them from scratch. That, not a dashboard, is what makes this adoptable. Then `AI-01` trace SDK. One task per loop iteration.
