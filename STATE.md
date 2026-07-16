# STATE — AgentGuard / Keel

A living snapshot of where the platform is. Dated narrative lives in `reports/`; this is the
"where are we right now" page. Updated at the end of each cycle.

_Last updated: 2026-07-16 (end of Phase 3)._

## The one-line claim

A real, current model (`gemini-2.5-flash`) will obey a prompt injection and attempt a $9,000
refund when its system prompt merely says "be helpful" — and AgentGuard blocks that deploy,
with evidence, without executing anything. A built-in library finds such risks even when the
customer wrote no tests.

Reproduce it: `gcloud auth application-default login && RUN_VERTEX_EVAL=true make eval-live`.

## What exists and is proven

| Capability | Where | Proven by |
|---|---|---|
| Multi-tenant control plane, DB-enforced isolation (RLS) | `src/keel`, migrations 0001 | `tests/test_isolation.py` |
| Agent registry + content-addressed fingerprint | `keel/fingerprint.py`, migration 0002 | `tests/test_fingerprint.py` |
| Deterministic evaluation engine + deploy gate | `keel/evals/{checks,engine,runner}.py`, migration 0003 | `tests/test_gate_blocks_dangerous_agent.py` |
| Real model execution (Vertex/Gemini), tool interception, evidence | `keel/evals/{live,providers}`, ADR 0009 | `tests/test_vertex_live.py` (live) |
| **Failure scenario library + risk report** | `keel/evals/{library,taxonomy,risk}.py`, migration 0004, ADR 0011 | `tests/test_library.py`, `test_risk.py`, `test_scenario_library.py`, live scan |

The gate is **fail-closed** throughout: unevaluated, zero-scenario, and errored states are
`unknown`/`errored`, never a pass.

## Product flow (what a customer does)

```
register agent → add version (manifest) → import library (or write scenarios)
   → run a scan (real model) → GET /risk?fingerprint=…  →  allowed | blocked | unknown
```

The verdict is keyed to a fingerprint, so it belongs to an exact configuration and a new
version cannot inherit an old version's pass.

## Attack coverage (library v2026.07.1)

7 of 8 taxonomy categories have probes: prompt injection, data exfiltration, privilege
escalation, unsafe tool use, financial abuse, policy violation, sensitive data exposure.
**`hallucinated_action` is a deliberate, tested gap** — it needs a check type we have not
built, and a weak probe would erode trust in the gate.

## Honest limits (the things a demo must not oversell)

1. **Simulation fidelity.** Tool results are canned; a scan tests decision-making against a
   scripted world, not the customer's real backend. This is the main way a passing verdict
   could still be wrong.
2. **Coverage is a floor.** The library reduces "did you think of this?" risk; it does not
   eliminate it.
3. **One model provider.** Portability is a design property (a Protocol), not yet tested
   (ADR 0010).
4. **The merge gate is advisory.** GitHub branch protection needs a paid plan on this private
   repo; a local pre-push hook stands in. `docs/branch-protection.md`.

## Delivery state

- `main`: DO-01 → BE-01 → CI gate (#1) → BE-02 (#2) → EVAL-01 (#3) → EVAL-02 (#4).
- Open: **Phase 3 (scenario library)** — PR to be opened this cycle.
- Every merge is a human gate; nothing auto-merges.

## Next

**Recommended:** grow the library (the moat compounds with coverage) and add a
`hallucinated_action` check type. **Then** Sprint 3 (trace storage, risk scoring over time,
dashboard). A dashboard now would visualise a detection layer whose coverage is still the real
constraint — content first, chrome later.
