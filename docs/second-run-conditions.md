# Second-Run Conditions

**Frozen:** 2026-07-25, before any instrumentation work begins.
**Status:** Written before results were known.

---

## Trigger

SchoolBot emits OTel GenAI spans (agent, tool, model) end to end — via Vertex instrumentation or equivalent — such that any external tool consuming OTLP can observe the full trajectory (tool names, arguments, ordering, model identifiers) for any chat request.

Until this trigger is met, no second run is warranted and no re-evaluation of the CONTRIBUTE verdict occurs.

---

## Scope

Re-run **E2, E3, E4 only**, on the same 5 scenarios from the original teardown (`mh-01`, `mh-02`, `car-01`, `car-02`, plus one additional if available from the RAGAS set).

- **E2:** Regression detection on an unchanged agent — does EvalView still report a false regression when trajectory data is present?
- **E3:** Tool-selection true-positive — can EvalView observe and diff a real tool-selection change?
- **E4:** Model-swap attribution — does EvalView detect and attribute a model version change?

No new gaps introduced. The gap set remains G1–G4 as frozen in the original pre-registration.

Re-verify **G3** against the then-current EvalView release, since the payload-redaction asymmetry may be patched between now and the second run.

---

## Reopen criteria

**Reopen BUILD** only if ≥2 of G1–G4 fail IN PRACTICE on clean trajectory data despite being PRESENT in source.

Concretely: if EvalView's noise model (G1) or cassette system (G2) fails to function correctly on real OTel-instrumented trajectory data from SchoolBot, that converts a source-level PRESENT into a practical ABSENT, potentially changing the tally.

**Otherwise CONTRIBUTE is permanent and the AgentGuard product line is closed.**

---

## What this document is not

This is not a roadmap for AgentGuard development. This is a pre-registered condition under which the CONTRIBUTE verdict could be revisited. The instrumentation work (adding OTel GenAI spans to SchoolBot) is worth doing for SchoolBot's own testability regardless of the AgentGuard decision.
