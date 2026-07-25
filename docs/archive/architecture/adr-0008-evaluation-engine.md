# ADR 0008 — Evaluation engine: simulate the agent, never run it

**Status:** accepted · **Date:** 2026-07-16 · **Task:** EVAL-01

## Context

The prime directive: *connect an agent → run reliability tests in CI → get a failure report
→ block the deploy.* BE-02 delivered the registry and the fingerprint. This decides how an
agent is actually evaluated.

The question that decides whether AgentGuard is a product: **can it catch a dangerous agent
behaviour before a real company deploys it?**

## The core problem

An `agent_versions.manifest` holds prompts, tool **schemas**, a model id and params. It does
not hold the tools' implementations — `issue_refund` is the customer's code, calling the
customer's payment API.

So "run the agent and see if it's safe" is a contradiction. Running it for real means a test
suite that issues real refunds, emails real customers and mutates real records. The failure
we exist to prevent would be caused by the thing meant to prevent it.

## Decision

**Simulate the agent's decision-making; never execute its side effects.**

```
agent_versions.manifest          eval_scenarios
(prompts, tool schemas,          (input + simulated tool
 model, params)                   responses + checks)
        │                                │
        └───────────────┬────────────────┘
                        ▼
                  AgentRunner
        drives the model with the manifest's
        prompts + tool SCHEMAS only
                        │
          agent decides to call a tool
                        │
                        ▼
        ┌───────────────────────────────┐
        │  the tool is NEVER invoked.   │
        │  the scenario's canned result │
        │  is returned instead.         │
        └───────────────────────────────┘
                        │
                        ▼
              AgentOutput (text + attempted tool calls)
                        │
                        ▼
                     checks
        assert on what the agent TRIED to do
                        │
                        ▼
         EvalResult -> EvalRun -> gate decision
                    (keyed by fingerprint)
```

The agent's *intent* is the signal. An agent that tries to refund $9,000 in response to an
injected instruction has already failed — whether or not the money moved. Observing the
attempt in a sandbox is strictly better than observing the consequence in production.

## Why this differentiates

The tools surveyed for BE-02 (LangSmith, Langfuse, Braintrust, TruLens, DeepEval, Ragas)
are overwhelmingly **observability and scoring** products: they record what an agent did,
usually in production, and score outputs — largely text quality (relevance, groundedness,
hallucination) via LLM-as-judge. They answer *"how good was that answer?"* after the fact.

AgentGuard asks a different question, before the fact: *"what would this agent **do**, and
should it be allowed to?"* Three consequences:

1. **The unit of judgement is the tool call, not the text.** "Refunded $9,000 to an
   unverified account" is a *correct-sounding* sentence. Text scoring rates it well. The
   danger is entirely in the action.
2. **The verdict must be deterministic.** A gate that blocks a deploy has to be defensible
   and reproducible. LLM-as-judge scoring is neither: it varies run to run and cannot be
   explained to an engineer whose deploy was blocked at 2am. Our checks are assertions —
   `must_not_call_tool`, `tool_arg_limit` — with a literal answer. LLM-judging can come
   later for *text* quality; it must never gate a deploy on its own.
3. **The result is keyed to a fingerprint**, so a verdict belongs to an exact configuration.
   That is what makes "this config passed" a claim rather than a vibe.

## Consequences

**Good**
- Evaluation is safe by construction: no customer side effects are reachable.
- Deterministic verdicts, reproducible in CI, defensible to a blocked engineer.
- Results attach to fingerprints, so unchanged configs need not be re-run.

**Costs, stated plainly**
- **Simulation fidelity is a real limit.** We test the agent's decision-making against
  *canned* tool results. If the real `lookup_order` returns a shape the scenario didn't
  anticipate, we tested a fiction. This buys safety at the cost of realism, and the gap is
  the main thing that could make a passing verdict wrong.
- Scenario authoring is work the customer must do. Phase 3's failure library is what makes
  that tractable; without it, adoption stalls at "write your own tests" — which is the
  thing they already don't do.
- We do not observe production behaviour, so we cannot catch drift that only appears with
  real data. That is a different product surface (tracing, `AI-01`).

## Alternatives rejected

- **Execute real tools in a sandbox.** Highest fidelity, but requires running customer code,
  which is a container-escape problem and an enormous surface. Not at Sprint 0. Revisit
  when there is a sandbox story.
- **Score production traces only.** That is observability — what everyone else sells, and it
  is inherently after the fact. It cannot block a deploy, because by then the agent is
  deployed.
- **LLM-as-judge as the gate.** Non-deterministic and unexplainable. See above.

## Scope of EVAL-01

In: scenarios, checks, runs, results, the gate decision keyed on fingerprint, tenant
isolation, and a `ScriptedRunner` that replays a fixed transcript.

Out (next): `LiteLLMRunner` for real model execution (EVAL-02), async workers (runs execute
synchronously for now — honest and simple; the queue lands when run times demand it), the
failure library (Phase 3), the SDK/CLI (Phase 5).

> **Read this honestly:** EVAL-01 proves the *detection* layer — that given an agent's
> behaviour, we catch the dangerous ones and block the deploy. It does not yet prove we can
> elicit that behaviour from a live model. `ScriptedRunner` is a test double, and a test
> double cannot validate itself. EVAL-02 closes that gap.
