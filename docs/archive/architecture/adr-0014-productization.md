# ADR 0014 — Productization: the demo experience & report (Phase 6.1)

**Status:** accepted · **Date:** 2026-07-17 · **Builds on:** ADR 0008–0013

## Context

The five-phase wedge works, but a person cannot yet *see* a result or reproduce the flow, and
we have not audited production-readiness. Phase 6's temptation is a dashboard. The steer — and
the right call — is: the highest-value first step is the **demo experience + a report**, not a
login/SPA dashboard over a detection layer whose coverage is still the real constraint.

## Decision

Ship three things and audit a fourth.

### 1. A scan report is the minimal "dashboard"

`agentguard scan --html report.html` renders the verdict the way a person understands it:
agent, model, fingerprint, the policy in effect (with provenance), the decision, each finding
with its **evidence**, and a concrete **remediation**. Plus `--report-json` for machines.

- **Self-contained HTML** — inline CSS, no external requests. It opens offline, attaches to a
  PR or ticket, and leaks nothing to a CDN when viewed. A test asserts no external references.
- **Everything dynamic is HTML-escaped.** A finding detail is arbitrary agent output; rendered
  raw it would make the report an XSS vector — the opposite of a security tool. Tested with a
  `<script>` payload.
- **Remediation is per-`check_type`**, deterministic. The report is only useful if it says what
  to *do*, not just what failed.

This delivers the visualization value of a dashboard for a fraction of the surface and none of
the new auth/session risk. A real dashboard can come once coverage — not chrome — is the
bottleneck.

### 2. A one-command reproducible demo

`make demo` runs the whole loop locally: bring up Postgres, start the API, register a
"Customer Support Bot", attach a $100 refund policy, add a prompt-injection scenario, and
`agentguard scan` → **BLOCKED** + an HTML report. Deterministic (scripted) by default;
`DEMO_RUNNER=vertex` runs it against a real Gemini. Everything is torn down on exit.

This is the "developer installs → registers → policy → scan → blocked" flow, made real and
repeatable — the thing a first customer runs to believe the product.

### 3. A quickstart

`docs/quickstart.md`: zero to a blocked deploy in one command, plus the manual flow and the CI
pointer.

### 4. A production-readiness audit (not a rewrite)

`docs/production-readiness.md` — an honest audit across auth, authz, isolation, secrets,
logging, monitoring, migrations, API stability. Done **inline**, because after building all
five phases the full context lives here; a cold audit agent would re-derive it worse. The
audit *names* gaps (observability, RBAC, rate limiting are the top three) rather than
pretending they don't exist, and frames each as pilot-acceptable vs GA-blocking. Fixing them is
future work; the value this cycle is the honest map.

## Explicitly not built

- **A login/SPA dashboard** — the report is the minimal visualization; a dashboard is chrome
  until attack coverage grows.
- **Server-side HTML endpoints** — the CLI renders client-side; no new auth surface.
- **Library expansion** — the corpus already covers the categories; growing it is its own cycle.
- **The audit's fixes** — observability/RBAC/rate-limiting are named and scoped, not
  implemented here. Building them silently would be the "fake feature" the brief forbids.

## Consequences

- **Good:** a first customer can install, run one command, and *see* a blocked deployment with
  evidence and a fix. No new persistence, no new auth surface, no migration.
- **Costs:** the report is client-rendered (no shareable hosted view yet); the audit's gaps are
  real and now visible — which is the point.
