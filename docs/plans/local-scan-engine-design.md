# Local Scan Engine — Design Exploration

**Planning only — do NOT implement.** Founder decision (003): build local scanning
mode for availability + DX first; authoritative signed verdicts (Ed25519) are later
work. This explores the architecture, grounded in the current engine.

## How evaluation works today (audited)
- **Verdict pipeline** (`evals/engine.py`): a `runner` produces agent output →
  `evaluate(checks, output)` applies **deterministic** checks → `decide(results)`
  returns a **fail-closed** verdict (no scenarios→UNKNOWN, any error→UNKNOWN,
  blocking-severity→BLOCKED). `engine.py:101-125`.
- **Checks are deterministic assertions** (`evals/checks.py`), and the check library
  is universal by construction (adr-0011). Policy compiles to checks (adr-0012,
  `policy/compiler.py`).
- **Runners** split cleanly: scripted/manifest runs are deterministic and need no
  model; the **live** runner uses Vertex via ADC (`config.py:30-36`, `evals/live.py`)
  — cloud + credentials + cost.
- **Verdict identity:** keys on a fingerprint (`fingerprint.py`); optionally
  **HMAC-signed** (`signing.py`), which *itself documents Ed25519 as the upgrade* for
  the third-party non-repudiation a portable verdict needs (`signing.py:8-10`).
- **Persistence/DB, usage limits, audit, metrics** are control-plane side today; per
  adr-0013 the CLI `scan` **calls the API** for the verdict.

## The five questions
**1. What can safely run locally?** The deterministic static checks over a
manifest/scripted run — `tool_arg_limit`, disallowed provider/model/tool, output-
marker assertions. Pure functions of manifest+policy (adr-0011) → identical verdict
anywhere.

**2. What requires cloud?** (a) live-model simulation (Vertex/ADC, cost); (b) the
policy source-of-truth + compilation; (c) verdict persistence, audit, metrics,
usage/billing.

**3. What can be cached?** The **compiled** policy (org→agent resolved, adr-0012),
stored locally with a **fingerprint/version** so staleness is detectable; refreshed
from the control plane.

**4. What must never leave the machine?** In offline mode, the customer's
manifest/agent details — local scanning should not require uploading the manifest.
(The privacy win Gemini flagged.)

**5. How does trust work without signatures?** By **trust zone** (the 003
reconciliation): a verdict produced *and consumed inside the same protected CI job*
has a small tamper surface and can be authoritative without asymmetric signing. A
verdict that must travel (laptop→CI, or cross-org) needs **Ed25519** — the
`signing.py` upgrade. Founder decision keeps authoritative designation for that later
stage.

## Staged design (proposal, not implementation)
- **Stage A — `agentguard scan --local` (advisory, availability-first).** Run the
  deterministic checks against a locally-cached compiled policy; emit the same
  verdict shape; **advisory by default**; optional cloud-audit sync ships
  verdict+fingerprint back (protects observability). Removes the cloud round-trip for
  the check itself → CI no longer blocked by control-plane downtime.
- **Stage B — Ed25519 signed verdicts (authoritative, later).** Sign local verdicts
  with a private key; the CI gate verifies with the published public key → portable
  authoritative verdicts. Gated on the signing work; this is where "authoritative
  local" is earned.

## Mandatory guards (whenever built)
- Stamp the **policy fingerprint/version** into every verdict (anti-drift, anti-
  stale-cache bypass).
- Keep the **audit/telemetry path** back to the control plane (don't regress
  observability).
- **Simulate-never-execute holds:** static checks local; live-model simulation stays
  cloud/credentialed (adr-0008).

## Verify before building (open questions)
- **The CLI source is in the standalone PyPI package, not this repo branch**
  (commits #17-19). Confirm there whether the gate currently runs the eval in-CI or
  calls the cloud API (adr-0013 says it calls the API) — this sizes Stage A.
- Define the compiled-policy cache format + fingerprint/version + invalidation.
- Decide the offline-vs-audit-sync default (privacy vs. observability tradeoff).

## Explicit non-goals now
No Ed25519 implementation, no "authoritative" designation, no offline live-model
simulation, no new engine — Stage A **reuses** `evals/engine.py` + `checks.py`.
