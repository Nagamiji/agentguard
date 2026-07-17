# ADR 0010 — Model provider abstraction (TDR for the LiteLLM deviation)

**Status:** accepted · **Date:** 2026-07-16 · **Relates to:** EVAL-02 (ADR 0009)

> This doubles as the **Technical Deviation Record** `CLAUDE.md` requires: the stack pins
> **LiteLLM** for model access, and EVAL-02 shipped a direct **Vertex AI** provider instead.
>
> Filed here as `docs/architecture/adr-0010-…` rather than the suggested
> `docs/adr/ADR-004-…`: this repo's ADRs already live in `docs/architecture/` numbered from
> 0008, so `ADR-004` in a new directory would collide with that scheme and fragment the log.

## Context

The reliability gate must run against whatever model a customer actually uses — Anthropic,
Vertex, Bedrock, OpenAI. `CLAUDE.md` names LiteLLM as the intended one-adapter-reaches-all
layer. EVAL-02 needed *real* model validation fast, and the environment already had Google
Cloud credentials, so it shipped a direct Vertex provider over `google-auth` + `httpx`.

## Decision

1. **The abstraction is a Protocol, not a framework.** `BaseModelProvider`
   (`src/keel/evals/providers/base.py`) is the only seam: `generate(system, messages, tools,
   params) -> ProviderResponse`. Everything above it — interception, checks, the gate, the
   library — is provider-agnostic and has no idea which model answered.
2. **The production provider today is Vertex AI Gemini.** It is the one implementation, and
   it is real (validated end-to-end in ADR 0009).
3. **LiteLLM stays a future adapter, not a present dependency.** When a second provider is
   actually required, a `LiteLLMProvider` (or an Anthropic/Bedrock one) implements the same
   Protocol and nothing above it changes. We do **not** pull LiteLLM in now.
4. **No abstraction beyond the Protocol until a second provider forces it.** No provider
   registry framework, no config-driven plugin loading, no capability-negotiation layer. The
   Protocol + a one-line `get_provider(name)` is the whole abstraction.

## Why not build the LiteLLM layer now

Because we have exactly one provider, and an abstraction validated against one implementation
is a guess. Building the multi-provider machinery before a second provider exists would be
speculative generality: we would be designing for Bedrock's and OpenAI's tool-calling quirks
without having met them, and every such guess is a line of code that has to be unlearned when
reality disagrees. The Protocol is the cheap, reversible commitment; the framework is the
expensive, sticky one. We take the cheap one and stop.

The honest cost of this choice, recorded plainly: **"supports multiple providers" is a
design property, not a tested one.** The second provider will surface assumptions the Vertex
implementation baked in (message-role mapping, how tool results are threaded, safety-filter
semantics). That is expected, and cheaper to pay once than to guess at now.

## Consequences

- **Good:** minimal surface, one real provider, credentials via ADC (no key in code), and a
  clear seam that a second provider slots into.
- **Cost:** portability is unproven until someone writes provider #2. The `test_vertex_live`
  suite is Vertex-specific; a provider-contract test suite is owed when #2 lands.

## Revisit when

A customer needs a non-Vertex model, **or** the single-provider assumption blocks a deal. At
that point: add the provider, extract any Vertex-specific assumptions the Protocol leaked, and
write a shared provider-contract test. Not before.
