# Production-readiness audit

_2026-07-17, end of Phase 6.1._ An honest audit of what is solid, what is a gap, and what is
deliberately deferred — done inline with full knowledge of every design decision in the repo.

Framing: **pilot** = a design partner running it, with the vendor operating the platform.
**GA** = self-serve, unattended, at scale. Several gaps are fine for a pilot and blockers for GA.

| Area | State | Notes |
|---|---|---|
| **Tenant isolation** | ✅ Solid | RLS `ENABLE`+`FORCE` + a `tenant_isolation` policy on **every** tenant table; the app connects as non-superuser `keel_app`; isolation tested per table. The transaction-scope trap (querying after `commit` drops the GUC) is handled by building responses from held objects. This is the strongest part of the system. |
| **Authentication** | ✅ Solid | Keys are `ag_<256-bit>`, SHA-256-hashed (no salt — deliberate: high-entropy keys don't need stretching; documented in `security.py`), shown once, revocable. |
| **Secrets** | ✅ Solid | `KEEL_*` env only; Vertex via ADC (no key in code); signing secret in env. gitleaks runs in CI **and** as a pre-commit hook. No secret has ever been in the tree. |
| **Migrations** | ✅ Solid | Linear alembic 0001–0005; every migration's up/down roundtrip is tested; RLS + grants handled; `ALTER DEFAULT PRIVILEGES` fixes new-table grants as a class. |
| **Reproducibility / evidence** | ✅ Solid | Verdicts key on fingerprint; runs are append-only with results + (real runs) the model trace; policy versions are immutable. |
| **No real tool execution** | ✅ Solid | Structural, not a policy (ADR 0008): the runner has no execution path; a test asserts the absence. |
| **Authorization (within an org)** | ⚠️ Gap | Every API key has **full org access** — no RBAC, no read-only or per-project keys. Fine for a single-team pilot; needed before multiple teams share an org. |
| **Monitoring / observability** | ⚠️ Gap (biggest ops gap) | Structured JSON logs + request-id + `/healthz`/`/readyz`, but **no metrics, no tracing, no alerting**. OTel is in the stack vision, unimplemented. A pilot the vendor watches is fine; unattended GA is not. |
| **Rate limiting / abuse** | ⚠️ Gap | None. No per-org request limits; the `rate_limit` policy rule is declared-not-enforced. 256-bit keys make credential brute-force infeasible, but there is no throttle on cost (a customer could run unbounded scans). |
| **API stability** | ⚠️ Partial | `/v1` prefix, Pydantic response models, additive-only changes so far. No written versioning/deprecation policy and no contract tests against the OpenAPI schema. |
| **Deploy-merge gate (this repo)** | ⚠️ Known | Advisory — GitHub branch protection needs a paid plan on a private repo; a local pre-push hook stands in (`docs/branch-protection.md`). |
| **Verdict signing** | ⚠️ Scoped | HMAC = symmetric integrity for a key-holder, **not** third-party non-repudiation. Asymmetric (Ed25519) is the documented upgrade. |
| **Policy override loosening** | ⚠️ By design | Lower scope can loosen a higher ceiling; visible via provenance; a `locked` flag is the mitigation (ADR 0012). |
| **Simulation fidelity** | ⚠️ Inherent | Tool results are canned; a scan tests decision-making against a scripted world. The main way a passing verdict could still be wrong (ADR 0008). |
| **Async / scale** | ⚠️ Deferred | Runs are synchronous. Fine while scans are seconds; a large real-model scan will want a job model. |
| **Project-scoped policies** | ⚠️ Deferred | Agents aren't linked to projects; project scope is rejected at the API (ADR 0012). |

## The short list before GA

1. **Observability** (metrics + tracing + alerting) — the top gap.
2. **RBAC / scoped API keys** — before multiple teams share an org.
3. **Rate limiting / cost controls** — bound what one org can spend.
4. **Enforce the merge gate** on this repo (GitHub Pro or public).
5. Async job model for large real-model scans.

## Acceptable for a first pilot

Tenant isolation, auth, secrets, migrations, the fail-closed gate, the CLI/Action, and the
report are all solid enough for a design partner the vendor operates for. None of the gaps
above is a data-safety hole — they are operational and multi-tenant-at-scale concerns.
