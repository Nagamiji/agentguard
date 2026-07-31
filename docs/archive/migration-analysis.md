# Migration Analysis — Current Codebase → AgentGuard Core

**Status:** Proposed (final architecture decision, pending Founder approval)
**Author:** Lead Architect (Claude)
**Date:** 2026-07-25
**Related:** `architecture-decision-record-v1.md`, `security-package-migration.md`, `implementation-roadmap-v2.md`
**Does not replace:** `docs/migration-plan.md` (retained as the migration trail).

> **Rule honored: DO NOT DELETE.** Nothing here proposes deleting files. "DEPRECATE" means *stop depending on it in the core path and stop investing*, retained in-tree (or split to a separate repo) until it is genuinely unused. No source is modified by this document.

---

## Legend

- **KEEP** — moves to core largely as-is; it already embodies the target design.
- **MOVE** — relocate to a new home (core lib, `agentguard-security`, or commercial layer) with light change.
- **MODIFY** — keep the logic, but decouple it (usually from FastAPI/DB) or change its interface.
- **DEPRECATE** — not part of the open core; stop investing. Retained, not deleted. Candidate for the later commercial layer or removal in a future major.

---

## Component-by-component

### CLI — `cli/src/agentguard_cli/` — mostly KEEP (this is the future front door)
| File | Verdict | Reasoning |
|---|---|---|
| `main.py` (commands: fingerprint, scan/evaluate, report, policy, init) | **MODIFY** | Already the local entry point. Reshape command surface to `init · snapshot · run · diff · test · report` (`cli-experience-v1.md`). Keep the offline-first wiring. |
| `local.py` (offline scan → Proof Objects, INCOMPLETE without live) | **KEEP** | Already implements the honest static/INCOMPLETE behavior we mandated. Becomes the backbone of `agentguard test` static path. |
| `proof.py` (`ProofObject`, `compute_evidence_digest`) | **KEEP** | This *is* the Proof Object + evidence hash. Core, unchanged interface. |
| `scenarios.py` (`BUNDLED_SCENARIOS`, `LocalScenario`) | **MODIFY** | Logic is right; format is wrong. Replace in-code scenarios with the YAML loader (`scenario-system.md`); keep the dataclass as the parsed in-memory type. Bundled security scenarios MOVE to `agentguard-security`. |
| `report.py` (`render_json`, `render_html`) | **KEEP** | Pure reporters, offline HTML — exactly the model. Register as core reporters. |
| `sarif.py` (SARIF 2.1.0) | **MOVE** | Reporter; security-flavored. Ship via `agentguard-security` (or core reporters + security scenarios). Keep as-is. |
| `api.py` (calls the backend) | **DEPRECATE** | Talks to the SaaS control plane; not part of local-first core. Retain for the optional commercial client later. |
| `agentguard_core/fingerprint.py` | **MODIFY** | See duplication below — collapse the two fingerprint implementations into this one canonical core module. |

### Fingerprinting — KEEP (dedupe first)
| File | Verdict | Reasoning |
|---|---|---|
| `agentguard_core/fingerprint.py` **and** `keel/fingerprint.py` | **KEEP + DEDUPE** | The two are **identical duplicates** (confirmed). Canonicalize on the `agentguard_core` copy as the single core module; `keel/fingerprint.py`'s importers repoint to it. Algorithm (`prompts/tools/model/params/retrieval/framework` → canonical JSON → SHA-256) is correct and deterministic — this is `fingerprint.algo = agentguard-fp-1`. **Do not fork the algorithm during the move** (would break existing fingerprints). |

### Evaluation engine — `src/keel/evals/` — MOVE to `agentguard.core`, MODIFY to decouple
| File | Verdict | Reasoning |
|---|---|---|
| `checks.py` (deterministic predicates) | **KEEP/MOVE** | The heart of honest gating; no DB coupling. Move to `agentguard.core.checks`. Add cost/latency/token checks (`scenario-system.md`). |
| `engine.py` (orchestrate runner → checks → report) | **MODIFY/MOVE** | Keep orchestration; sever any request/DB context so it runs on a local record. |
| `runner.py` + `live.py` (`LiveAgentRunner`, intercepts tools) | **KEEP/MOVE** | **Critical gap-closer:** the live runner currently exists *only in the backend*, which is why the CLI can only do static checks. MOVE it into core so `--runner live` works locally. Tool-interception safety property preserved. |
| `library.py` (`LibraryScenario` tuples) | **MODIFY** | Scenario *content* is valuable; the in-code format is replaced by YAML. Security scenarios → `agentguard-security`; reliability/quality/cost seeds → `community/scenarios`. |
| `taxonomy.py` (ASI/LLM mapping) | **MOVE** | Belongs to `agentguard-security` (it's the security taxonomy). |
| `risk.py` (fail-closed rollup, worst-severity, coverage) | **KEEP/MOVE** | Implements the fail-closed gate + coverage vector we require. Move to core; ensure it emits the coverage *vector*, not a score. |
| `providers/` (`base.py`, `vertex.py`) | **MODIFY** | Provider abstraction stays; core ships a minimal set (OpenAI/Anthropic) via optional extras. `vertex.py` retained behind an extra. |

### Policy engine — `src/keel/policy/` — MOVE (to security/gate layer)
| File | Verdict | Reasoning |
|---|---|---|
| `compiler.py`, `rules.py`, `resolver.py` | **MOVE/MODIFY** | This is the deployment gate (manifest findings + derived checks). Decouple from DB-stored policies; read policy from a local file. Ships as part of `agentguard-security` / gate feature. Logic KEPT. |

### FastAPI backend — `src/keel/main.py`, `src/keel/api/*` — DEPRECATE from core
| File / area | Verdict | Reasoning |
|---|---|---|
| `main.py`, `api/agents.py`, `api/evals.py`, `api/policies.py`, `api/orgs.py`, `api/projects.py`, `api/dashboard.py`, `api/audit.py`, `api/lookups.py`, `api/health.py` | **DEPRECATE** | Multi-tenant control plane. Not part of local-first core. **Retained** for the optional commercial/team layer (Phase 5), not deleted. The *evaluation logic* they wrap is already being lifted into core (above), so nothing of value is lost by deprecating the HTTP shell. |
| `policy_service.py` | **DEPRECATE** | Server-side policy service; superseded by local policy files in core. |

### Data / infra — DEPRECATE from core (SaaS-only)
| File / area | Verdict | Reasoning |
|---|---|---|
| `models.py` (`Organization`, `Agent`, `AgentVersion`, `EvalRun`, `EvalResult`, `Policy`, `ApiKey`, `UsageEvent`, `AuditEvent`, …) | **DEPRECATE (core) / MOVE (commercial)** | DB entities exist for multi-tenancy/billing/registry. Core state is files in `.agentguard/`, not Postgres. Entities retained for the commercial team layer. |
| `schemas.py` (pydantic DTOs) | **MODIFY** | Split: the *domain* schemas that describe a record/proof/gate move to core (aligned to `agent-record.json`); the *API* DTOs stay with the deprecated backend. |
| `db.py`, `migrations/`, `alembic.ini` | **DEPRECATE** | No DB in core. Retained for commercial layer. |
| `security.py`, `signing.py`, `roles.py`, `rate_limit.py`, `provisioning.py`, `middleware.py`, `audit.py`, `deps.py`, `context.py`, `net.py` | **DEPRECATE (core)** | Auth, RBAC, tenancy, rate-limiting, request context — all SaaS concerns. **Exception:** `signing.py` — evaluate whether its HMAC signing can be reused for the record's `evidence.signature` (**MODIFY/MOVE** the signing primitive into core if so; deprecate the request-auth parts). |
| `config.py`, `logging.py`, `metrics.py` | **MODIFY** | Core needs a *small* local config (`.agentguard/config.toml`) + logging. Reuse patterns, drop server/env-heavy pieces. |
| `edge-worker/`, `src/worker/` | **DEPRECATE** | Edge/gateway + background worker — SaaS infra. Retained, not in core. |

### Reports directory — `reports/` — KEEP as fixtures/examples
Existing generated reports become **example artifacts** under `community/examples/` to show what output looks like.

---

## Duplication & risks flagged

1. **Two identical `fingerprint.py`** (`agentguard_core` vs `keel`). Must collapse to one *before* the move, or the two will drift and produce mismatched fingerprints. Highest-priority cleanup.
2. **Live runner only in the backend** (`keel/evals/live.py`). Until it's moved to core, the CLI physically cannot do `--runner live`; the whole "measure real behavior" story depends on this move. Phase-1/2 critical path.
3. **Scenario content trapped in code** (`BUNDLED_SCENARIOS`, `library.py`). The content is an asset; the format is a liability. Migrate content to YAML, don't rewrite the scenarios.
4. **`schemas.py` is doing double duty** (domain + API). Splitting it cleanly is the fiddliest MODIFY; do it deliberately so core doesn't drag in FastAPI types.

## Net effect

Everything that makes AgentGuard *honest and useful* (checks, risk rollup, fingerprint, proof/evidence, live-runner interception, reporters, taxonomy) is **KEEP or MOVE** — it survives. Everything that makes it a *SaaS* (auth, tenancy, DB, billing, HTTP) is **DEPRECATE from core**, retained for a later commercial layer. No deletions. The core that emerges is the local-first tool the product definition demands, assembled almost entirely from code that already exists.
