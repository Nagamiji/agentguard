# ADR 0011 — The failure scenario library

**Status:** accepted · **Date:** 2026-07-16 · **Task:** Phase 3 · **Builds on:** ADR 0008, 0009

## Context

EVAL-01/02 proved AgentGuard catches dangerous behaviour *a customer describes*. But the
honest limit stated at the end of EVAL-02 was: **detection is only as good as the scenario
library, and a customer will not write attacks from scratch — that is the thing they already
don't do.** This closes that gap.

The strategic point: calling a model is a commodity. A maintained corpus of agent attacks,
mapped to a severity taxonomy and runnable against *any* agent with zero configuration, is
not. This is the moat.

## Decision

Ship a built-in library of attacks (`src/keel/evals/library.py`) that a customer applies to
their agent in one call, plus a risk report that aggregates a scan into a verdict.

### 1. Universal by construction — the hard part

A built-in attack cannot know a customer's tool names or policies. So every probe's check is
decidable **without that knowledge**, using one of two techniques:

- **Planted marker.** The attack plants a synthetic marker in content *we* control (a pasted
  document, a poisoned tool result) and the check asserts the marker never appears in output
  (`must_not_output`). If it leaks, the agent was exfiltrated or injected. The marker is
  synthetic, so naming it in evidence leaks nothing real.
- **No-action request.** The attack pairs a request that legitimately needs no tool ("what
  are your hours?") with an injected instruction to act. Any tool call at all
  (`must_not_use_tools`) means the injection steered the agent — decidable without knowing
  what the tool *does*.

Both are how PyRIT/Garak-style probes work, adapted to AgentGuard's "judge the action, not
the prose" stance (ADR 0008).

### 2. The taxonomy is the product vocabulary

Eight categories (`src/keel/evals/taxonomy.py`): prompt injection, data exfiltration,
privilege escalation, unsafe tool use, financial abuse, hallucinated action, policy
violation, sensitive data exposure. It is its own module because the taxonomy is part of what
we sell, not an implementation detail.

### 3. Coverage is 7 of 8, and the gap is named, not hidden

v1 ships probes for seven categories. **`hallucinated_action` has no probe**, on purpose:
detecting "claimed success with no matching tool call" needs a check type combining output
and tool-call state, which we do not have. A weak keyword probe ("said 'done'") would fire on
innocent phrasing, and false alarms are how a gate loses the trust that makes it worth
having. An empty-but-named category is more honest than a bad probe, and a test
(`test_hallucinated_action_is_a_known_gap_not_a_silent_one`) makes adding one a deliberate
act.

### 4. One adaptive probe, the rest universal

Indirect injection via a poisoned tool result (OWASP LLM01 — the vector agents are least
hardened against) needs a tool to poison. It is generated from the agent's declared tools at
import and dropped for a tool-less agent, rather than shipped to fail as an error. A probe
that cannot apply is not a finding; padding a report with N/A rows trains people to ignore it.

### 5. Reuse, don't rebuild

Library scenarios materialise into the existing `eval_scenarios` table (`source='library'`,
`library_version` recorded) and run through the existing run/gate machinery. The only new
storage is two provenance columns (migration 0004). The risk report is a read-side
aggregation over existing results.

### 6. The library is versioned in code, not per tenant

`LIBRARY_VERSION` is a constant, bumped when the corpus changes; every scan records it. The
library is content *we* ship, so it versions with the code — exactly like `FINGERPRINT_ALGO`.
This is not per-tenant data and does not belong in a table.

### 7. Risk aggregation fails closed

`classify()` (`src/keel/evals/risk.py`) is pure. An errored or unscanned configuration is
`unknown`, never a clean bill of health; an unrecognised severity is treated as blocking. Same
posture as the gate: "we could not tell" must never read as "it's fine".

## Validated

Against a live `gemini-2.5-flash`, a scan of a weakly-prompted refund agent — **using only
built-in attacks the customer never wrote** — returned `blocked`, catching a critical prompt
injection (`KEEL-PWNED-OVERRIDE`) and a policy-override declaration. That is the Phase 3
claim: we find risks the customer did not think to test for.

## Consequences

- **Good:** zero-config value on day one; a taxonomy customers can reason in; the moat is
  content we control and can grow without customer work.
- **Costs / honest limits:**
  - **Simulation fidelity, still** (ADR 0008): tool results are canned. A universal probe
    tests decision-making against a fiction we authored.
  - **Coverage is a floor, not a ceiling.** Seven categories, one adaptive probe. A confident
    customer could still ship a failure mode the corpus does not probe. The library reduces
    "did you think of this?" risk; it does not eliminate it, and the risk report says so by
    only ever reporting on what it actually ran.
  - Markers are fixed strings; a model specifically trained to recognise `KEEL-*` could game
    them. Per-scan randomisation is a future hardening step.

## Next

A `hallucinated_action` check type; per-scan marker randomisation; growing the corpus (the
moat compounds with coverage); and eventually customer-private scenario packs.
