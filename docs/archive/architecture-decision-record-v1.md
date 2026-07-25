# Architecture Decision Record v1 — AgentGuard Core

**Status:** Proposed (final architecture decision, pending Founder approval)
**Author:** Lead Architect (Claude)
**Date:** 2026-07-25
**Related:** `product-definition-v1.md`, `agent-record-format-v1.md`, `migration-analysis.md`

---

## Context

AgentGuard is pivoting from a SaaS AI-agent security-testing control plane (FastAPI + Postgres + multi-tenant RBAC, package `keel`) to a **local-first, open-source agent reliability tool** whose primitive is a single file: `agent-record.json`. This ADR fixes the component architecture, the data flow, and the boundaries between the open core and everything built on top of it.

## Decision (summary)

1. The core is a **local CLI + library**, no server required. State lives on disk in `.agentguard/`.
2. There is **one canonical artifact**, `agent-record.json`, and every other component is a *producer* or *consumer* of it.
3. The pipeline is: **Record → (optionally) Evaluate against Scenarios → Diff → Report**, each stage reading/writing the record.
4. The FastAPI backend, DB, auth, and billing are **not part of core**; they move to an optional commercial layer (see `migration-analysis.md`).
5. Security capabilities become a **package on top of core**, not the product (see `security-package-migration.md`).

---

## System Overview

```
   Developer
      │  writes / changes prompts, models, tools, logic
      ▼
   Agent  (any framework: OpenAI SDK, Anthropic SDK, LangGraph, custom)
      │  is observed by …
      ▼
┌──────────────────────────────────────────────────────────────┐
│                  AgentGuard Recorder                          │
│  (decorator / SDK auto-trace / OTel ingest / manual builder)  │
└──────────────────────────────────────────────────────────────┘
      │  emits the canonical artifact
      ▼
   agent-record.json  ◀── the primitive (git-committable, signable)
      │
      ├──────────────► Scenario Engine ──► adds `evaluation` block
      │                (reliability / security / quality / cost)
      │
      ├──────────────► Diff Engine ──────► compares two records
      │                (fingerprint + behavior delta)
      │
      └──────────────► Reporters ────────► JSON · HTML · SARIF · JUnit · terminal
```

All arrows are files in, files out. There is no hidden database in the core path; `.agentguard/runs/<id>/` is the store.

---

## Component-by-component

### 1. The Developer (actor)
The startup AI engineer. Interacts only through the CLI and the record file. Never required to create an account or run a server for the core loop.

### 2. The Agent (external, not ours)
The system under test. AgentGuard is framework-agnostic and does **not** provide a runtime. The agent is whatever the developer built. We only need to observe: the agent's *definition* (prompts, model, tools, params) and, for a run, its *behavior* (input, output, tool calls, metrics).

### 3. AgentGuard Recorder
Turns an agent into an `agent-record.json`. Three ingestion levels (detailed in `integration-strategy.md`):

- **L1 — Manual wrapper:** `@agentguard.record` decorator / context manager around an agent call. Explicit, zero-magic, works everywhere.
- **L2 — Automatic tracing:** thin adapters that hook the OpenAI SDK, Anthropic SDK, LangChain/LangGraph callbacks to auto-populate the record.
- **L3 — Universal export / ingest:** import from OpenTelemetry GenAI / OpenInference spans (OTLP JSON) or any source that can produce the fields. This makes AgentGuard a *sink* for the existing tracing standard rather than a competitor to it.

Two record *kinds*:
- `kind: "snapshot"` — the agent *definition* only (prompts, model, tools, params, fingerprint). No execution. Cheap, deterministic, always available offline. This is what `agentguard snapshot` produces.
- `kind: "run"` — a snapshot **plus** one executed interaction (input, output, tool_calls, metrics). Requires actually invoking the agent (live runner).

**Determinism boundary:** the *snapshot / fingerprint* is fully deterministic and offline. The *run* involves a model call and is therefore governed by the "threshold-over-N" determinism rule (a live verdict is stable only when it holds over N repetitions), inherited from the prior product-truth review and **preserved**.

### 4. `agent-record.json` (the primitive)
The single source of truth. Full schema in `agent-record-format-v1.md`. Design invariants:
- **Portable:** self-contained JSON, no external refs required to read it.
- **Diffable:** canonical key ordering; behavior-relevant fields separated from cosmetic ones so diffs are meaningful.
- **Signable:** carries `fingerprint` (deterministic identity of the agent definition) and optional `evidence` (content digest + signature).
- **Versioned:** `schema_version`, plus `engine_version` and `scenario_lib_version` inside `evaluation`.

### 5. Scenario Engine
Reads a record (or executes one) and evaluates it against declarative scenarios across four categories — **reliability, security, quality, cost** — using deterministic **checks** (no LLM-judge in the gate path by default). Writes results into the record's `evaluation` block as **Proof Objects** plus a **coverage vector** and a **gate decision**.

Reuses the existing engine logic (`keel/evals`: `engine.py`, `checks.py`, `risk.py`, `taxonomy.py`, `live.py`) refactored into `agentguard.core` and decoupled from FastAPI/DB. The **live runner intercepts tool calls** (never executes real tools) — a safety property that is **preserved**. Full design in `scenario-system.md`.

Hard rules preserved from prior decisions (non-negotiable):
- Static/structural runs **must not** emit a PASS for behavioral scenarios — they report `SKIPPED — requires --runner live` and the gate is `INCOMPLETE` (exit `40`), never `0`.
- Coverage is a **vector** ("3/10 ASI surfaces tested; untested: …"), never a single score.
- Verdict vocabulary is honest: `STATIC CHECK`, `BEHAVIOR SIMULATION` (live), `ALLOWED` / `BLOCKED` / `INCOMPLETE`, `deployment gate`. Banned: "verified", "secure", "static simulation" as a pass.

### 6. Diff Engine
The headline developer feature. Given two records, it answers *"what changed and does it matter."* Two layers:
- **Identity layer (deterministic):** compares `fingerprint.agent_fingerprint`. If equal, the agent *definition* is behaviorally identical by construction. If different, it localizes the change to prompts / model / params / tools / retrieval / framework.
- **Behavior layer (when both are runs / evaluations exist):** compares outputs, tool-call sequences, metrics (latency, tokens, cost), and per-scenario Proof Object verdicts (new failures, fixed failures, flipped gates).

Output is designed to be pasted into a PR: *what changed · why it matters · confidence · affected tools · behavior differences*. Full spec in `cli-experience-v1.md`.

### 7. Reporters
Pure functions from a record (or a diff) to an output format. Reuse existing `report.py` (JSON + self-contained HTML) and `sarif.py` (SARIF 2.1.0). Add **JUnit XML** for CI. Reporters never mutate the record. This keeps CI integration a formatting concern, not a core concern.

---

## Data flow & storage

- **Store:** `.agentguard/` in the repo root.
  - `.agentguard/runs/<run_id>/record.json` — records.
  - `.agentguard/baseline.json` (or a git ref) — the record to diff against.
  - `.agentguard/config.toml` — project config (scenario dirs, redaction policy, runner defaults).
  - `scenarios/` (repo-level) — user + community scenarios (see `scenario-system.md`).
- **No network in the core loop** except the model provider call *inside* a live run (opt-in, `--runner live`). Snapshot, diff, report, and static checks are fully offline.
- **Secrets** (provider API keys) are read from env only, used transiently for a live run, and **never written into a record** (see `agent-record-format-v1.md` §privacy).

---

## Cross-cutting invariants (apply to every component)

1. **Local-first, cloud-optional.** No component in the core path may require a server, account, or network (other than an opt-in live model call).
2. **One artifact.** No component invents a competing on-disk format; everything is expressed as producing/consuming `agent-record.json`.
3. **Honest by construction.** No component may fabricate a PASS or a single score; the honesty rules above are enforced at the type/exit-code level, not by convention.
4. **Forward-compatible.** Consumers tolerate unknown fields and reject only on incompatible `schema_version` MAJOR.
5. **Framework-neutral.** No component hard-depends on LangChain (or any single framework).

---

## Consequences

- **Positive:** tiny surface area, offline-first, trivially CI-integrable, a real chance at becoming a standard because the artifact is self-contained and framework-neutral.
- **Cost:** we give up the SaaS control plane's central registry/history *in the core* — history now lives in git and `.agentguard/`. Central/team features become a later commercial layer, not a dependency.
- **Risk:** the live-runner determinism problem (model non-determinism) is real; mitigated by threshold-over-N and by making the deterministic snapshot/fingerprint the default, always-available surface.

## Alternatives considered (and rejected)

- **Keep the SaaS control plane as core.** Rejected: contradicts local-first and open-source-adoption-first; server dependency kills the 5-minute wedge.
- **Adopt OTLP as our primary artifact.** Rejected: OTLP is a *wire/trace* format optimized for streaming spans to a backend, not a diffable, signable, git-committed *decision artifact*. We *ingest* OTLP; we don't store it as the primitive.
- **LLM-judge in the gate path.** Rejected for the default gate: non-deterministic, un-auditable. LLM-judge may exist as an *optional, clearly-labeled* quality check, never as the gate.
