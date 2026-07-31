# TOMBSTONE — AgentGuard

**Verdict:** CONTRIBUTE
**Date:** 2026-07-25
**Decision type:** Pre-registered, mechanically applied.

---

## What AgentGuard was

An open-source developer toolkit for capturing, comparing, testing, and understanding AI agent behavior — positioned as a merge-time regression gate for agent-powered applications.

## The three framings it passed through

1. **Security scanner** (early 2026) — a tool that scans agent configurations for prompt injection, data exfiltration, privilege escalation, and unsafe tool use. Built a working eval engine with real Vertex/Gemini model execution, a failure scenario library, a policy engine, and a CLI deployment gate with SARIF output.

2. **Agent security platform** (mid-2026) — expanded scope to multi-tenant SaaS with an agent registry, content-addressed fingerprinting, tenant isolation via RLS, and a cloud deployment target. Added a Cloudflare edge worker, Docker infrastructure, and an API surface.

3. **Agent behavior toolkit** (late July 2026) — pivoted to the "snapshot → diff → gate" model for agent behavior regression testing. Introduced the `agent-record.json` format as a proposed core primitive, designed a plugin/adapter/scenario architecture, and positioned against observability tools (LangSmith, Langfuse) and eval frameworks (Promptfoo, DeepEval).

## What killed it

Three findings from the competitive teardown, in order of severity:

1. **The category is occupied.** EvalView ships the same three commands (`init`/`snapshot`/`check`), the same CLI shape, the same positioning paragraph, and the same "snapshot then diff" primitive — on PyPI, on GitHub Marketplace, with a domain. AgentAssay ships the statistical verification the planned MVP lacked. Promptfoo (now OpenAI) already shipped trajectory assertions with OTLP ingestion.

2. **Three of four hypothesized gaps are already filled upstream.** G1 (noise model): PRESENT in EvalView and AgentAssay. G2 (cassette replay): PRESENT in AgentAssay. G4 (in-PR baseline approval): PARTIAL in EvalView. Only G3 (payload redaction) is ABSENT across all tools — one gap, not a product.

3. **The chosen primitive was a serialization format, not a primitive.** `agent-record.json` fails its own disappearance test: remove it and the product still works on OTel spans, JSONL, SQLite, or any other format. OpenTelemetry's CNCF-graduated GenAI semantic conventions already define the vendor-neutral schema that every competitor adopted.

## The one real finding

G3 — EvalView ships PII detection (`ExpectedOutput.no_pii`, `PIIEvaluation`) but persists captured output verbatim into baseline files it instructs users to commit. The asymmetry between detection and persistence is a real defect, documented in [g3-reproducer.md](g3-reproducer.md) with a fully synthetic reproduction. This finding belongs upstream as a disclosure, not as a competing product.

## Links

- **Competitive teardown:** [competitive-teardown.md](competitive-teardown.md) (ratification block prepended)
- **G3 reproducer:** [g3-reproducer.md](g3-reproducer.md) (synthetic, public-safe)
- **Second-run conditions:** [second-run-conditions.md](second-run-conditions.md) (frozen pre-registration for when SchoolBot has OTel instrumentation)
- **Final architecture review:** [archive/final-architecture-review.md](archive/final-architecture-review.md) (archived — ecosystem architecture for the closed product line)
- **Archived product/architecture docs:** [archive/](archive/) (moved, not deleted)

## Tracked items (not implemented in this task)

1. **SchoolBot WAF bypass.** Production is reachable via UA-spoofed requests past Cloudflare rule 1010. Proposed fix: allowlisted test header or a dedicated staging target, so future testing never requires bypassing the WAF.

2. **SchoolBot trajectory instrumentation.** SchoolBot emits no per-step trajectory data. Proposed fix: OTel GenAI spans (agent/tool/model) via Vertex instrumentation. Worth doing for SchoolBot's own testability regardless of the AgentGuard decision.

## Outcome

The one contribution this project produced was an upstream finding in EvalView: the tool's PII detection features and its baseline persistence are disconnected, creating an asymmetry where recognized PII is written unredacted to files the tool instructs users to commit. The finding was reproduced on EvalView 0.8.0 (current as of 2026-07-25) with fully synthetic data.

Disclosure draft: [g3-disclosure-draft.md](g3-disclosure-draft.md). Status: drafted, pending review, not yet sent. Recommended channel: GitHub Security Advisory per EvalView's SECURITY.md.

No other implementation threads remain open for the AgentGuard product line.
