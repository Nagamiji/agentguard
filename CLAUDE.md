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
- **The library is universal by construction** (`adr-0011`): a probe's check never needs the customer's tool names — it asserts over output (a planted synthetic marker must not leak) or over the fact of a tool call (a no-action request that acts was manipulated). `GET /v1/library`, `POST /agents/{id}/scenarios/import`, `GET /agents/{id}/risk`. Coverage is a floor, and `hallucinated_action` is a named, tested gap — not a silent one.
- **Limits are policy, not hardcode** (`adr-0012`). A policy at an org/agent scope compiles into checks the engine applies (`max_tool_arg: $100` → a `tool_arg_limit` check on every scan) plus static manifest violations (disallowed provider/model/tool). Precedence is org → agent, lower wins, and **provenance is recorded because a lower scope can loosen a higher ceiling**. `DEPLOY_ENFORCED` rules compile; `RUNTIME_DECLARED` ones (rate/geo/token-budget/approvals) are stored and surfaced as deferred, never pretended-enforced; unknown rules are rejected. `POST /v1/policies`, `GET /v1/agents/{id}/policy`.
- **The deployment gate is the CLI** (`adr-0013`, `src/agentguard_cli/`). `agentguard scan` calls the API and **its exit code is the CI contract** (`0 allowed · 20 blocked · 10 error · 30 unknown`), fail-closed by default. It emits SARIF 2.1.0 (findings land in the PR) and the composite Action (`.github/actions/agentguard/`) uploads it even on failure. Verdicts are optionally HMAC-signed (`KEEL_SIGNING_SECRET`, `keel/signing.py`) — symmetric integrity, not third-party attestation. Guide: `docs/deployment-gate.md`.
- **The report is the minimal visualization** (`adr-0014`, `src/agentguard_cli/report.py`). `agentguard scan --html` renders a self-contained (no external requests), fully HTML-escaped report — agent/model/fingerprint, policy with provenance, verdict, evidence, and a per-finding remediation. `make demo` runs the whole loop end to end. **A dashboard is deliberately not built** — it's chrome until attack coverage, not visualization, is the bottleneck.

## Current state
See `STATE.md` for the live snapshot and `docs/production-readiness.md` for the honest audit (solid: isolation/auth/secrets/migrations; top gaps: observability, RBAC, rate limiting). On `main`: the full five-phase wedge; this cycle added the demo experience + report.

## Where to build next
Validated 2026-07-17: `make demo` runs register → policy → scan → **BLOCKED** + a self-contained HTML report; a person can now see and reproduce the product.
Next, from the production-readiness audit (in priority order): **observability** (metrics/tracing/alerting — the top gap), **RBAC / scoped API keys**, **rate limiting / cost controls**. Then publish the CLI, async/webhooks, asymmetric signing, the policy `locked` ceiling, an `agent.project_id` link, and growing the attack library. Do not build features the audit doesn't call for. One task per loop iteration.
