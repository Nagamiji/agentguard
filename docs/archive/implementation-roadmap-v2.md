# Implementation Roadmap v2

**Status:** Proposed (final architecture decision, pending Founder approval)
**Author:** Lead Architect (Claude)
**Date:** 2026-07-25
**Related:** all `*-v1.md` in this decision set; `migration-analysis.md`
**Does not replace:** `docs/implementation-roadmap.md` (retained as the prior trail).

> Sequencing principle: **ship the primitive and the diff first.** Nothing else has value until a developer can produce and compare `agent-record.json`. Each phase is independently useful and independently shippable.

---

## Phase 1 — Agent Record · Snapshot · Diff

**Goal:** `pip install agentguard` → `snapshot` → change code → `diff`. The primitive exists, is portable, deterministic, and diffs meaningfully. Fully offline.

**Why now:** This is the wedge and the standard. Without it nothing downstream matters; with it, even alone, a startup AI engineer gets value (definition-level regression awareness in their PRs). It's also almost entirely assembled from existing code (fingerprint, proof, report).

**Scope:** `agent-record.json` schema (`agent-record-format-v1.md`); `init`, `snapshot`, `diff`, `report` (JSON/HTML); L1 manual wrapper (`@agentguard.record`); dedupe the two `fingerprint.py`; `.agentguard/` store.

**Success criteria:**
- 5-minute cold start, no account, produces a useful record.
- `diff` output is PR-paste-ready (what changed · why · confidence · affected tools).
- Fingerprint is stable across runs and reproducible on another machine.
- JSON Schema + conformance fixtures published.

**Intentionally delayed:** live model execution, scenarios, framework auto-tracing, any server. Diff is *definition-level* only here (identity + field deltas), which is honest and still valuable.

---

## Phase 2 — Scenario Testing

**Goal:** `agentguard test` evaluates a record against declarative YAML scenarios across all four categories, with the honest gate (`ALLOWED`/`BLOCKED`/`INCOMPLETE`) and coverage vector. Behavior-level diff (`--behavior`) turns on.

**Why now:** Once records exist, "did it get *worse*" is the next question. This is where reliability/quality/cost regression testing lands and where the fail-closed gate (already built in `risk.py`) becomes usable locally.

**Scope:** YAML scenario schema + loader (replacing `BUNDLED_SCENARIOS`); MOVE the **live runner** (`keel/evals/live.py`) into core — the critical unblock; checks library (+ cost/latency/token checks); coverage vector; gate + exit codes (0/30/40); JUnit reporter; threshold-over-N determinism for live verdicts.

**Success criteria:**
- `--runner live` works locally (no backend).
- Static run of a behavioral scenario reports `SKIPPED` + `INCOMPLETE` (exit 40) — never a fake PASS.
- Coverage reported as a vector with untested surfaces named.
- CI can gate on the exit code in one line.

**Intentionally delayed:** framework adapters (still L1/L3 only), community marketplace, multi-agent, LLM-judge gating.

---

## Phase 3 — Framework Integrations

**Goal:** L2 auto-tracing adapters (OpenAI SDK, Anthropic SDK, LangChain, LangGraph single-agent) + L3 OTel/OpenInference ingest.

**Why now:** With record + test proven valuable, reduce activation energy so adoption widens beyond hand-instrumented agents. Ingesting OTel lets already-instrumented teams onboard for free.

**Scope:** adapter entry-point contract; `agentguard[openai|anthropic|langchain]` extras; `snapshot --from otel`; published adapter conformance test.

**Success criteria:**
- Each adapter produces a record identical in shape to L1.
- An OTel-emitting team gets a record with zero new instrumentation.
- Adapters degrade honestly (missing field absent, never guessed).

**Intentionally delayed:** multi-agent/graph fan-out; exotic frameworks (left to community).

---

## Phase 4 — Community Ecosystem

**Goal:** the plugin ecosystem opens — scenario sets, adapters, reporters as installable plugins; `community/` repo live; reference known-good/known-bad agents; scenario CI.

**Why now:** Core + integrations are stable enough to be a *contract*. Now let others extend without core-team bottleneck. This is where growth compounds.

**Scope:** entry-point plugin API (`agentguard.scenarios|adapters|reporters`); conformance suite published; contribution ladder + governance; scenario-discrimination CI (must pass on good agent, fail on bad).

**Success criteria:**
- A third party ships an `agentguard-*` plugin without core-team involvement and it auto-registers.
- ≥1 framework author emits `agent-record.json` natively.
- The version triple (`schema`/`scenario`/`engine`) keeps old records/plugins working across a core minor bump.

**Intentionally delayed:** anything requiring central hosting; a hosted scenario registry (files + pip suffice first).

---

## Phase 5 — Security & Enterprise Packages

**Goal:** `agentguard-security` (OWASP ASI suite, prompt-injection/tool-misuse scenarios, SARIF evidence, signed attestation, deployment-gate policy) as the flagship plugin; the optional commercial governance/team layer (org history, policy management, SSO) on top.

**Why now:** Last, deliberately. The security/AppSec value + Proof-Object moat convert to revenue *after* the open standard has adoption and engineers already use the core bottom-up. Leading with this would invert the adoption strategy.

**Scope:** MOVE security scenarios + taxonomy + policy engine into `agentguard-security` (see `security-package-migration.md`); HMAC attestation in core, Sigstore as V2 upgrade (in-band via `signature.scheme`); revive the deprecated backend selectively as the commercial team layer.

**Success criteria:**
- `pip install agentguard-security` adds a full ASI test suite as scenarios on the same record.
- Signed, reproducible evidence artifact binds a fingerprinted agent to its proofs.
- Coverage vector + honest vocabulary preserved end to end.

**Intentionally delayed:** heavy enterprise (RBAC/billing/multi-region) only as real demand appears — never ahead of adoption.

---

## Final Review Questions

**1. What developer pain does AgentGuard uniquely solve?**
"I changed my prompt/model/tool and I have no idea if my agent got worse — and no artifact in my repo that says so." AgentGuard makes *behavioral change* a first-class, diffable, git-committed object, answering *what changed · did it regress · can I ship it* inside the existing git/CI workflow. No one else produces that artifact.

**2. Why install this instead of LangSmith / Langfuse / Promptfoo?**
- **LangSmith / Langfuse / Braintrust** are cloud-first *observability* — they tell you what happened in production, in their dashboard, after the fact. AgentGuard is local-first, pre-merge, and its output is a *file in your repo*, not a row in a SaaS. It *ingests* their world (via OTel) rather than competing with it.
- **Promptfoo** is the closest (local, file-oriented) but emits a *flat test report*, not a portable, fingerprinted, signable **behavior record** you diff across commits. AgentGuard adds agent identity (fingerprint), a diff command, deterministic reproducibility, and signed evidence — none of which Promptfoo standardizes.
- The one-liner: *they measure; AgentGuard records, diffs, and gates — locally, in git.*

**3. What becomes the open-source standard?**
`agent-record.json` — a portable, framework-neutral, diffable, signable file for agent behavior. The bet (validated by research: no such standard exists in 2026) is that this becomes to agents what SARIF is to static analysis and the commit object is to code.

**4. What creates community growth?**
Four low-friction contribution surfaces on one stable format: **scenarios** (YAML PRs), **adapters**, **reporters**, **examples** — all as install-to-activate plugins (the pytest model). Plus a mechanical compatibility contract (conformance suite + version triple) so the ecosystem scales without the core team as a bottleneck. Every producer added deepens the value of the one primitive.

**5. What is the long-term moat?**
Two layers. (a) **Standard gravity:** once `agent-record.json` is what frameworks emit and CI gates on, the format is the moat — switching costs accrue to the ecosystem, not a feature. (b) **The Proof Object + signed evidence:** the honest, reproducible, attestable evaluation artifact that turns the standard into a *trusted deployment gate* — the commercial layer competitors can't easily copy because it depends on the format adoption underneath it. Adoption protects the moat; the moat monetizes the adoption.

---

## The five governing preferences (how every tie was broken)

| Prefer | Over | Where it shows up |
|---|---|---|
| Simple workflow | More features | 6-command CLI; Phase 1 is just record+diff |
| Transparent reproducibility | Automatic magic | No fake PASS; honest vocab; human-confirmed drafts; deterministic checks over LLM-judge |
| Open-source adoption | Enterprise complexity | Developer-first wedge; enterprise is Phase 5 |
| Local-first | Cloud dependency | No account/server in the core loop; `.agentguard/` on disk |
