# Product Definition v1 — AgentGuard

**Status:** Proposed (final architecture decision, pending Founder approval)
**Author:** Lead Architect (Claude)
**Date:** 2026-07-25
**Supersedes emphasis of:** `docs/product-direction.md`, `docs/product-review-v2.md` (does not delete them; see §7)

---

## 1. What is AgentGuard?

> **AgentGuard is version control and regression testing for AI agents.**

One sentence, filled in:

> **AgentGuard is Git + pytest + OpenTelemetry for AI agents** — an open-source, local-first tool that records what an agent *does* into a portable, diffable, signable file (`agent-record.json`), then tells you exactly what changed and whether the change is safe to ship.

The unit of value is a single primitive: the **Agent Behavior Record** (`agent-record.json`). Everything else — scenarios, diffing, gating, security — is built on top of that one file.

The mental model:

| Ecosystem | Primitive | AgentGuard equivalent |
|---|---|---|
| Git | commit object | **`agent-record.json`** |
| pytest | test result | `evaluation` block inside the record |
| OpenTelemetry | trace / span | ingest source (we consume OTel GenAI spans, we don't replace them) |
| SARIF | static-analysis finding | Proof Object (security package) |

AgentGuard is the missing artifact between "I changed my prompt" and "is my agent still trustworthy?"

---

## 2. The problem (stated precisely)

Developers change five things constantly:

1. **Prompts** — a reworded system prompt.
2. **Models** — `gpt-4o` → `claude-opus-4-8`, or a temperature bump.
3. **Tools** — a new tool, a changed tool schema, a widened permission.
4. **Agent logic** — control flow, retries, routing.
5. **Workflows** — multi-step orchestration.

After any of these, they cannot answer three questions:

- **"What changed?"** — diffs of `.py` files don't show *behavioral* change.
- **"Did my agent get worse?"** — no regression baseline exists.
- **"Can I trust this modification enough to merge/ship it?"** — no gate, only vibes.

Existing tools answer *"what happened in production"* (observability) or *"what's the average eval score"* (offline eval dashboards). None answer *"what changed between this commit and the last, and is it safe"* as a **local, git-committed, reproducible artifact**.

That gap is real and, as of 2026, unfilled: OpenTelemetry's GenAI semantic conventions standardize *runtime tracing*; Promptfoo produces a *flat test report*; LangSmith/Langfuse/Braintrust are *cloud-first*. Nobody produces a portable, deterministic, signable behavior record that lives in the repo and diffs cleanly. AgentGuard does.

---

## 3. Primary user

**Chosen: the startup AI engineer.**

The developer at a small-to-mid company who is *shipping* an agent into a product, owns a CI pipeline, and is on the hook when the agent regresses in production.

### Why this user, and not the others

| Candidate | Verdict | Reasoning |
|---|---|---|
| **Startup AI engineer** | ✅ **Primary** | Has a CI pipeline and a `git` habit (so `agent-record.json` fits their muscle memory). Ships often enough to feel regression pain weekly. Small enough to adopt a tool in an afternoon without procurement. Large enough to care about "did this break." This is the adoption wedge. |
| Solo AI developer | Secondary | Feels the pain but has weaker CI/collaboration needs and lower willingness to add tooling ceremony. They come along for free once the startup engineer's workflow exists — the local-first design serves them at zero extra cost. |
| Framework developer | Not the buyer | LangChain/LangGraph/CrewAI authors are an **integration target**, not a user. We want them to *emit* `agent-record.json`, not *buy* AgentGuard. Courting them as the primary user inverts the ecosystem strategy (see `integration-strategy.md`). |
| Enterprise platform team | Deferred (commercial) | This is the eventual *revenue* buyer for the security + governance packages (Phase 5). But they buy **after** the open-source standard exists and their engineers already use it bottom-up. Building for them first produces enterprise complexity before adoption — the exact inversion this pivot rejects. |

### Reconciling with the prior "AppSec-first, phased" decision

The prior review (`docs/plans/product-truth-review.md`, and the recorded positioning decision) landed on *"both buyers, phased — V1 for AppSec/Platform trust, V1.5 developer on-ramp."* This document **re-sequences that, it does not discard it:**

- The **open-source core** is developer-first (startup AI engineer). This is the top of the funnel and the standard-setting layer.
- The **evidence-based deployment gate + AppSec buyer** is preserved intact — it becomes the **`agentguard-security` package and the commercial layer built on the open core** (see `security-package-migration.md`). The Proof Object moat is *not* weakened; it moves up the stack to where the money is.

> **⚠ Founder decision point (Gate — product authority):** This re-sequencing reverses the *emphasis* of the prior "AppSec-first" call. I am recommending it because the new direction is explicitly "open-source adoption over enterprise complexity" and you cannot lead with the AppSec buyer *and* win bottom-up OSS adoption at the same time — the wedge has to be developer-first. **If you want to keep AppSec as the leading buyer, say so and I will re-order the roadmap.** Everything else in these documents is downstream of this one decision.

---

## 4. Non-goals — what AgentGuard will NOT become

Stated as hard boundaries so scope creep has something to hit:

1. **Not an AI observability platform.** We do not run dashboards over production traffic, alerting, or live monitoring. We *consume* OpenTelemetry GenAI / OpenInference spans as an ingest source; we do not compete with LangSmith/Langfuse/Datadog on runtime observability. Our artifact is a *committed file*, not a *time-series in a cloud*.
2. **Not a chatbot / agent framework.** We do not provide an agent runtime, orchestration, memory, or a way to *build* agents. We record and test agents built with *any* framework.
3. **Not a model provider or a gateway.** We never proxy inference. We call providers only inside the sandboxed live runner, and we intercept tool calls rather than execute them.
4. **Not "only a security scanner."** Security is one category built on the core (reliability, quality, cost are the others). Security is a *package*, not the product.
5. **Not a cloud dependency.** The core must run fully offline against local files. No account, no login, no server required to produce, diff, or verify a record. Cloud is an optional, later, commercial convenience — never a gate on the core loop.
6. **Not a "magic verdict" oracle.** We never emit a single "security score" or fake a PASS. We show evidence and let the human decide. Transparent reproducibility over automatic magic — always.
7. **Not a multi-agent / graph orchestration test harness (in v1).** Single-agent behavior first. Multi-agent is explicitly deferred.

---

## 5. What "good" looks like (definition of success for v1)

- A startup AI engineer installs `agentguard`, runs `agentguard snapshot`, and gets a useful `agent-record.json` in **under 5 minutes**, with **zero account creation**.
- `agentguard diff old.json new.json` produces output they'd paste into a PR review without editing.
- The record format is boring, stable, and documented well enough that a *framework author* can emit it without asking us.
- The word "AgentGuard" starts being used as a noun for the file, the way "a SARIF" or "a trace" is.

---

## 6. Positioning statement (canonical, reuse verbatim)

> **AgentGuard** is the open-source standard for recording and regression-testing AI agent behavior. It turns any agent — built with any framework — into a portable, diffable, signable `agent-record.json`, so you can answer *"what changed, did it get worse, and can I ship it?"* right in your git workflow. Local-first. No account required. Security, quality, and cost checks build on the same record.

---

## 7. Relationship to existing docs

This document is the **final product definition** and takes precedence on *positioning and primary user*. It intentionally does **not** delete or edit:

- `docs/product-direction.md`, `docs/product-review-v2.md` — retained as the review trail that produced this decision.
- `docs/plans/product-truth-review.md` — its **guardrails remain binding** (no fake PASS, no single score, honest vocabulary, human-confirmed verdicts). This doc re-sequences buyers; it does not touch those guardrails.

See `architecture-decision-record-v1.md` for the system design and `implementation-roadmap-v2.md` for sequencing.
