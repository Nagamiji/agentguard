# ADR 0012 — The policy engine

**Status:** accepted · **Date:** 2026-07-17 · **Task:** Phase 4 · **Builds on:** ADR 0008–0011

## Architecture review (done before building, as the mission asked)

A short, honest audit of what exists, and what Phase 4 should and should not touch:

- **Limits were hardcoded in scenarios.** A refund ceiling lived as `tool_arg_limit max=100`
  inside each scenario. That does not scale: an org cannot set one rule that governs every
  agent. This is exactly the debt Phase 4 removes — the engine now consumes a *compiled
  policy*.
- **`_get_agent` was duplicated** across `api/agents.py` and `api/evals.py`. The policy router
  would have made it three copies, so it was extracted to `api/lookups.py` (one shared
  `get_agent_or_404`). The two existing copies are noted for a follow-up cleanup; this cycle
  did not rewrite merged, working routers just to dedupe — but it did stop the growth.
- **Agents are not linked to projects.** BE-01 created `projects`, but `agents` carry only
  `organization_id`. So project-scoped policies *cannot resolve to an agent*. Rather than add
  a half-working project layer, project scope is accepted by the schema (forward-compatible
  `CHECK`) but **rejected at the API with a clear message**, and org + agent scopes are fully
  implemented. Fixing this needs an `agent.project_id` link — a small, separate change.
- Reuse held: policies reuse the agent/version immutability pattern, the RLS pattern, and the
  fingerprint idea. No new infrastructure.

## Decision

A policy declares what a scope is *allowed* to do; the engine compiles it and enforces it.

### 1. Scopes and precedence

`organization` and `agent` scopes (project deferred, above), each optionally targeting an
`environment` (dev/staging/prod). Precedence, lowest to highest: **organization → agent**,
and within a scope, **env-specific overrides env-agnostic**. Lower scope wins.

### 2. Provenance, because override precedence is a real risk

Lower-scope-wins means an **agent policy can loosen an org limit** (set the refund ceiling to
$1000 when the org said $100). That is the precedence the product specifies, and it is a
genuine hazard for a *security* control. The mitigation shipped now is **transparency**: every
resolved rule records the scope that set it, so `GET /agents/{id}/policy` shows
`max_tool_arg: from agent (overrides organization)`. The loosening is impossible to hide.

> **Recommended follow-up:** a `locked` flag on org policies so a ceiling cannot be loosened
> below, only tightened. Deferred deliberately — it is a policy-semantics decision worth making
> explicitly rather than baking in now. Until then, an org that needs hard ceilings should not
> grant agent-policy write access. This is written down, not assumed.

### 3. Two enforcement moments

The compiler (`keel/policy/compiler.py`) produces:

- **`derived_checks`** — check specs merged into every scenario run. `max_tool_arg` becomes a
  `tool_arg_limit` check; `forbidden_tools`/`allowed_tools` become `must_not_call_tool`;
  `max_tool_calls` becomes itself. **No limit is hardcoded anywhere** — the check is generated
  from the policy. This is the core requirement ("the engine consumes compiled policies").
- **`manifest_findings`** — static violations of the *declared* config, decided with no run:
  a disallowed `provider`/`model family`, or a forbidden/non-allow-listed tool the agent
  declares. These block immediately, even a scenario-less run.

### 4. Deploy-enforced vs runtime-declared — the honest split

A deploy-time, simulate-don't-execute gate can check the agent's declared config and what it
tries to do. It **cannot** check token spend over time, request rate, wall-clock latency,
geography, time-of-day, or human-in-the-loop approvals — those are runtime facts. So rules are
split: `DEPLOY_ENFORCED` compile into checks; `RUNTIME_DECLARED` are accepted, stored, and
surfaced as `deferred_runtime`, but the gate does not pretend to enforce them. Anything
unknown is **rejected at write time** — silently ignoring a typo'd rule is how a customer ends
up believing they are protected when nothing is enforced.

### 5. Immutable versions = audit history

A policy's rules live in append-only `policy_versions` (dedup + sequence by fingerprint, never
updated). Each run records the `policy_fingerprint` it enforced and the `environment`, so the
audit answers "what was enforced, when, by which policy version".

### 6. Fail closed

A static policy violation forces `blocked` even when scenarios pass, error, or are absent. In
risk aggregation an unrecognised severity blocks. "We could not tell" never reads as "allowed".

## Validated

- Deterministic (scripted): an org policy capping refunds at $100 **blocks a run whose
  scenario has no limit check** — proving the block came from the compiled policy, not the
  scenario. The same run without the policy is allowed.
- Static: a disallowed provider blocks a scenario-less run.
- **Live: a real `gemini-2.5-flash` attempted a $9,000 refund and the org policy blocked it**
  (`'issue_refund.amount' was 9000, above the permitted maximum of 100`) — the engine
  consuming a compiled policy against a real model.

## Consequences

- **Good:** one rule governs many agents; limits are centralised and audited; the gate is
  policy-driven, not hardcoded; the deploy/runtime split is honest.
- **Costs / limits:**
  - **Override precedence can loosen a ceiling** (mitigated by provenance; `locked` is future).
  - **Project scope is unimplemented** pending an agent→project link.
  - **Runtime rules are declared, not enforced** — that needs a runtime layer (a different
    product surface from the deploy gate).
  - Model-family matching is prefix-based (`gemini` matches `gemini-2.5-flash`) — simple and
    documented, not a full registry.
