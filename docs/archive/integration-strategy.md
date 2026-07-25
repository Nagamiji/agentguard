# Framework Integration Strategy

**Status:** Proposed (final architecture decision, pending Founder approval)
**Author:** Lead Architect (Claude)
**Date:** 2026-07-25
**Related:** `agent-record-format-v1.md`, `architecture-decision-record-v1.md`, `open-source-model.md`

---

## Principle: do NOT force LangChain

The record must be producible from *any* stack. If AgentGuard is perceived as "a LangChain thing," it cannot become a standard. We support three ingestion levels of decreasing coupling and increasing reach. **All three produce the exact same `agent-record.json`** — that sameness is the entire strategy.

```
L1  Manual wrapper      →  works everywhere, explicit, zero magic
L2  Automatic tracing   →  convenient, per-SDK adapters
L3  Universal export    →  ingest from OTel / OpenInference / anything
                            ─────────────────────────────────────────
                            all three ⇒  agent-record.json
```

---

## Level 1 — Manual wrapper (the floor, always works)

A decorator / context manager the developer puts around their agent call. No framework assumptions.

```python
import agentguard

@agentguard.record
def my_agent(user_message: str):
    ...
    return response

# or, explicitly:
with agentguard.record(name="refund-agent") as rec:
    rec.set_model(provider="anthropic", name="claude-opus-4-8", params={"temperature": 0})
    rec.add_tool("issue_refund", schema=issue_refund_schema)
    out = my_agent(msg)
    rec.set_output(out)
# → agent-record.json
```

Why it's the floor: it never breaks when a framework changes its internals, it's trivially auditable, and it embodies "transparent reproducibility over automatic magic." Every other level is a convenience over this.

---

## Level 2 — Automatic tracing (convenience adapters)

Thin, optional adapters that hook a known SDK's call path and auto-populate the record. Each is an installable extra (`pip install agentguard[openai]`) so the core stays dependency-free.

Planned support, in priority order (by adoption × ease of hooking):

| Adapter | Hook point | Fills |
|---|---|---|
| **OpenAI SDK** | client wrapper / `responses`+`chat.completions` | model, params, tools, messages, output, tool_calls, tokens |
| **Anthropic SDK** | client wrapper / Messages API | same |
| **LangChain** | `BaseCallbackHandler` | model, tools, intermediate steps → tool_calls |
| **LangGraph** | graph callbacks / checkpointer taps | node-level tool_calls (single-agent path only in v1) |

```python
import agentguard.integrations.openai as agi
client = agi.wrap(OpenAI())      # records every call it mediates
```

Adapters are **best-effort enrichers**: if an adapter can't determine a field, it leaves it absent rather than guessing (honesty invariant). Multi-agent/graph fan-out is explicitly **out of scope for v1** (single-agent behavior first).

---

## Level 3 — Universal export / ingest (the reach multiplier)

Anything that can be mapped to the fields can become a record. Two directions:

- **Ingest from OpenTelemetry GenAI / OpenInference:** consume OTLP JSON spans (`gen_ai.*` attributes: `gen_ai.request.model`, `gen_ai.usage.*`, prompt/response events; OpenInference `llm.input_messages`, `tool` spans) and project them into `agent-record.json`.
  ```bash
  agentguard snapshot --from otel ./trace.otlp.json
  ```
  This makes AgentGuard a **sink for the existing tracing standard**, not a competitor to it — a team already emitting OTel gets records for free.
- **Build directly:** the record is documented, boring JSON. A framework author can emit it from their own telemetry with no AgentGuard dependency at all. We publish a JSON Schema and a conformance test.

```
OTel/OpenInference spans ─┐
LangSmith/Langfuse export ─┤→  mapper  →  agent-record.json
Custom logs / your telemetry ┘
```

---

## Why this creates ecosystem growth

1. **No lock-in tax to adopt.** L1 works in an afternoon on any stack; L3 means teams with existing OTel/observability get records with zero new instrumentation. Low activation energy → wide adoption.
2. **The format, not the tool, spreads.** Because all three levels converge on one documented file, the *artifact* becomes the thing people standardize on — framework authors emit it to be "AgentGuard-compatible," which is free distribution for us.
3. **We ride the standard instead of fighting it.** By ingesting OTel GenAI rather than replacing it, we inherit its momentum (Datadog/AWS/GCP/Azure/MLflow adoption) and position one layer up — the *committed decision artifact* the trace standard doesn't provide.
4. **Adapters are a contribution surface.** New adapters (CrewAI, Autogen, Vercel AI SDK, …) are exactly the kind of self-contained plugin the community can own (see `open-source-model.md`), so reach grows without core team effort.
5. **Every level strengthens the same primitive.** More producers → more records in more repos → the diff/scenario/security value compounds on a single format. That compounding is the moat.
