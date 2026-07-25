# Product Reality Review v3 — AgentGuard

**Author:** Claude (Principal Engineer seat, Engineering Council)
**Date:** 2026-07-25
**Type:** Independent adversarial review. No code written. No source files modified.
**Status:** For founder decision.

> **Scope note the founder must read first.** This review was commissioned against the
> vision "open-source developer toolkit for capturing, comparing, testing, and
> understanding AI agent behavior, with `agent-record.json` as the core primitive." That
> review already exists twice in this repo — once as opinion
> ([`archive/final-architecture-review.md`](archive/final-architecture-review.md)) and once
> as **data** ([`competitive-teardown.md`](competitive-teardown.md), verdict CONTRIBUTE,
> ratified today in [`TOMBSTONE.md`](TOMBSTONE.md)). I did not know that when the task was
> framed. Writing a third opinion-based pass and presenting it as new is the single
> worst thing I could do here — opinion is *weaker* evidence than the install-and-run
> teardown that already settled it.
>
> So this document does something different and more useful: **it audits the verdict.**
> I treated the tombstone as a hypothesis that could be wrong, went and checked its
> external claims against primary sources, and found three factual defects. All three
> push the conclusion *further* from BUILD, not toward it. Details in §1 and §9.

---

## 1. Executive Summary

**The CONTRIBUTE verdict holds. I independently confirm it, and I think it was reached
partly for the wrong reasons.**

Three findings from my own verification pass:

**1.1 — The incumbent named as the killer is not the killer.** The teardown concluded "the
category is occupied" on the strength of EvalView shipping the same three commands. I
checked EvalView's actual adoption: **~124 GitHub stars** (`hidai25/eval-view`, 37
releases since 2025-12-03). AgentAssay: **~5 stars** (`qualixar/agentassay`). Feature
parity with a 124-star solo project is *not* an occupied category — that is a claimed
category, and claimed categories get taken all the time. Had EvalView been the only wall,
BUILD would have been arguable.

The actual wall is **Promptfoo, acquired by OpenAI on 2026-03-09** and being folded into
OpenAI Frontier. Promptfoo already ships `trajectory:tool-args-match`,
`trajectory:tool-sequence`, `trajectory:step-count`, **is an OTLP receiver** (port 4318),
and has **built-in Vertex AI instrumentation following the GenAI semantic conventions**.
That is the entire planned product, plus OpenAI's distribution, plus the one capability
the teardown thought nobody had. You do not win a CI-gate category against the company
that owns the model API your users are billed by.

**1.2 — The teardown's sharpest technical claim is probably false.** Its headline finding
was that *all four* tools are trajectory-blind against SchoolBot because SchoolBot uses
Vertex and emits no per-step data. Promptfoo was scored `[VERIFIED-source] /
[UNVERIFIED-live]` and dismissed because its `http` provider can't return a trajectory.
But the `http` provider is the wrong integration path — Promptfoo's supported path for
this is **OTLP ingestion with Vertex instrumentation**, which was never tested. The one
tool that could plausibly have observed SchoolBot's trajectory was ruled out on a path
its vendor doesn't recommend. This is the most consequential error in the teardown, and
correcting it removes the last argument for BUILD.

**1.3 — Two supporting claims in the tombstone are wrong on the facts.**
- "OpenTelemetry's **CNCF-graduated** GenAI semantic conventions" — they are **not
  graduated and not stable.** They live in a dedicated repo
  (`open-telemetry/semantic-conventions-genai`) with **no tagged releases**; every
  `gen_ai.*` attribute is still developmental. Practitioners pin to commits. The
  conventions win anyway — Datadog (v1.37+), Honeycomb, New Relic, Grafana, MLflow,
  CrewAI, AutoGen and Promptfoo all emit or ingest them — but the tombstone overstated
  the maturity of the thing it deferred to.
- G3 "payload redaction is ABSENT across all tools" is true **inside the four eval tools
  tested** and false **in the ecosystem**. Microsoft Presidio is the de-facto OSS
  redactor; OpenInference ships `OPENINFERENCE_HIDE_INPUTS` / `HIDE_OUTPUTS`; the OTel
  Collector's `attributes` and `transform` processors drop or hash span attributes before
  export; Gravitee, Bifrost and Truefoundry all redact in-line. G3 is a **composition** of
  existing parts, which is exactly why it is a disclosure and a PR, not a product. The
  tombstone reached the right conclusion on G3 with a slightly overstated premise.

**Net:** the pre-registered rule produced the right answer. Its evidence base had holes,
and every hole, when filled, argues harder for the same answer. That is the good case —
it means the decision is robust, not lucky.

**One procedural criticism, which matters for the next decision.** The gap set G1–G4 was
frozen before the experiment — correct practice — but all four gaps are *feature* gaps.
None asks about distribution, trust, or category ownership, and this repo's own earlier
review had already concluded that "distribution and trust" is "the actual moat in this
category, and the one you don't have"
([`final-architecture-review.md`](archive/final-architecture-review.md)). The teardown
therefore ran a rigorous experiment on the dimension that was already known not to be
decisive. It got the right verdict; a pre-registration that included one distribution
question would have gotten there in an afternoon instead of a day.

---

## 2. What Survives

Ranked by defensibility. Only four things survive, and only one of them is a product.

**2.1 — The G3 disclosure. Send it.** EvalView detects PII in agent output
(`ExpectedOutput.no_pii`, `PIIEvaluation`) and then writes captured output **verbatim**
(`core/golden.py:158`) into golden files it instructs users to `git add` and commit
(`core/celebrations.py:56-58`). The asymmetry between detection and persistence is a real
defect, reproduced on 0.8.0 with fully synthetic data
([`g3-reproducer.md`](g3-reproducer.md)). The draft exists
([`g3-disclosure-draft.md`](g3-disclosure-draft.md)) and **has not been sent.** This is
the highest return-on-effort item in the entire repository: it is finished work, it is
correct, it costs one email, and it is the only externally-visible output the project has
earned. Send it via GitHub Security Advisory per EvalView's SECURITY.md. Not sending it is
the single worst outcome available.

**2.2 — The teardown itself, as published work.** You did something almost nobody does:
installed four agent-testing tools and drove one of them end-to-end against a *real
production multi-agent Vertex application with real users*, then documented precisely how
each failed and pre-registered the decision rule beforehand. The write-up is honest to the
point of self-harm — it records two corrections that moved evidence against the author's
own preference, and refuses to reinterpret a non-registered finding into a favourable
verdict. That is rare and it is legible to exactly the audience you'd want. "I ran four
agent regression-testing tools against my production Vertex agent and all four were blind
to it" is a genuinely good post. Cost to publish: near zero. The work is done.

**2.3 — The trajectory-capture gap for Vertex/Gemini.** This is the one real technical
finding, and the pre-registration scored it zero because it wasn't G1–G4. The entire eval
ecosystem is OpenAI-shaped: EvalView's auto-tracer (`trace_cmd/patcher.py`) patches
OpenAI, Anthropic and Ollama only; `agentevals` calls
`_normalize_to_openai_messages_list` and branches on `output["tool_calls"]`, requiring
OpenAI/LangChain message shapes. Vertex/Gemini multi-agent applications are second-class
citizens in every tool tested. You are unusually well positioned to fix this because you
operate one. **But be clear about what it is:** OTel GenAI instrumentation for
Vertex/Gemini is infrastructure plumbing. It rides the standard instead of fighting it, it
makes your own product testable, it is a legitimate and useful contribution — and its
realistic ceiling is a few hundred stars and zero revenue. It is a calling card, not a
company. See §7.

**2.4 — SchoolBot.** Underweighted in every document in this repo. You have a *deployed*
AI product with real users (students), ~18 tools, a custom `MultiAgentOrchestrator`, and
RAG over pgvector. Almost everyone writing agent-reliability tooling in 2026 has no such
thing. The tooling category is contested by OpenAI; the "AI product with actual users"
category is not contested by anyone, because it's just hard work. If the goal is a
business rather than stars, SchoolBot is the asset and AgentGuard was the distraction.

**Also technically survives, with no strategic value:** the eval engine, the policy engine,
the SARIF output, the multi-tenant control plane, the RLS work, the Cloudflare edge worker,
`proof.py`. These are competently built. They are also the sunk cost, and their existence
is not an argument. Do not let 26 merged PRs vote on this decision.

---

## 3. What Dies

**Everything else. Specifically and without hedging:**

| Dies | Why |
|---|---|
| **`agent-record.json` as the core primitive** | Fails its own disappearance test — remove it and the product runs on OTel spans, JSONL or SQLite. A serialization format is the cheapest layer in any system. **And the name is already taken:** the IETF's 2026 Agent Identity Protocol draft uses `agent-record.json` for agent identity/public-key/policy. You would be fighting a standards body for a filename you didn't need. |
| **The toolkit / platform framing** | "Capture, compare, test, understand" is four products. Each has a funded incumbent. A solo effort that starts as four products ships zero. |
| **The plugin API, marketplace, scenario hub, reporter extensibility** | An extension API for zero extensions. pytest got plugins *after* becoming the default test runner; contribution was the reward for winning, not the strategy. Detailed refutation in §8. |
| **Level-2 SDK adapters (OpenAI / Anthropic / LangChain / LangGraph / CrewAI / Mastra)** | Six adapters is a permanent maintenance tax paid to six teams that ship faster than you and owe you nothing. This is the standard cause of death for solo OSS. |
| **Replay** | LangGraph owns it via checkpointing and time-travel, because replay needs framework-internal state you don't have. You lose this on the merits. |
| **"Simulate, don't execute"** | A deterministic simulated record can only report a change when you changed the code — and in that case `git diff` already told you. Instrument blind to the phenomenon it exists to detect. |
| **The multi-tenant SaaS control plane, billing, tenant provisioning, edge worker** | Infrastructure for customers who do not exist. Ship-blocking complexity with zero users. |
| **A community standard** | Standards are ratified by adoption you don't have, against conventions (OTel GenAI) that vendors already ship. Negative value: you'd be asking framework authors to emit a second format. |
| **Security as "one package"** | The pivot that demoted security to a plugin also demoted the only thing this repo ever had a defensible story about (the Proof Object). If security is a package, the moat is a package. |

**The three-month question, answered directly:** with 3 months, the smallest product people
would still love is **not a product**. It is: send the disclosure (day 1), publish the
teardown (week 1), instrument SchoolBot with OTel GenAI spans (weeks 2–4, worth doing
regardless), and spend the remaining two months on SchoolBot's actual users. If you must
ship OSS, ship the Vertex/Gemini OTel instrumentation from §2.3 — one package, one job,
no plugin API, no format, no gate.

---

## 4. Biggest Risks

**4.1 — Sunk-cost reversal (highest).** This repo contains 26 merged PRs, a working eval
engine, and a design lineage across three framings. The tombstone was ratified *today*.
The risk is not that the verdict was wrong; it is that the verdict gets quietly reopened
next week because the code exists and killing it feels wasteful. **The commissioning of
this very review is a mild instance of that pattern** — a request to re-review a vision
that was closed by data hours earlier. Note that I am not calling the request illegitimate;
re-auditing a fresh verdict is good practice, and it found three defects. But the
reopen criteria are already frozen in
[`second-run-conditions.md`](second-run-conditions.md), and the honest move is to respect
them: reopen on the trigger, not on discomfort.

**4.2 — Competing with your own model vendor.** Promptfoo is now OpenAI's. If you build a
CI gate for agents, your roadmap is a line item on the roadmap of the company whose API
your users call. This is structurally unwinnable for a solo maintainer.

**4.3 — Mistaking rigor for progress.** The pre-registration discipline in this repo is
genuinely excellent — better than most funded teams. It is also the thing most likely to
consume the next three months. A perfectly-designed second experiment against a
124-star competitor is still a day spent not shipping. Rigor is a tool for making
decisions cheaper, not a deliverable.

**4.4 — The Vertex instrumentation work quietly regrowing into a platform.** §2.3 is a
narrow, useful package. It has an obvious gravitational pull back toward "…and then a
diff engine, and then a gate." Write the scope down before starting and treat expansion
as failure.

**4.5 — Not sending the disclosure.** A found, reproduced, unreported security defect
decays. EvalView ships every few weeks; if it's fixed independently the finding becomes
worthless, and the one contribution this project produced becomes zero.

---

## 5. Biggest Opportunities

**5.1 — Be the person who made Vertex/Gemini agents testable.** The whole ecosystem
assumes OpenAI message shapes. Google's stack is a first-class production platform with
second-class eval support. Fixing that is narrow, verifiable, standards-aligned, and
nobody's roadmap. It also unblocks your own reopen criteria.

**5.2 — Redaction at capture time, as an upstream contribution.** The industry consensus my
research surfaced is "redact at the boundary" — user input, retrieved context, tool
arguments, model output, **before** persistence, because after-the-fact redaction is held
insufficient for GDPR / EU AI Act. Every eval tool tested persists raw. The parts already
exist (Presidio, OTel processors). Wiring them into the golden-file write path of the
tools people actually use is a real contribution with your name on it, and it's the
constructive twin of the G3 disclosure.

**5.3 — Credibility from the teardown.** The methodology is the asset. Pre-registered
decision rules applied against your own preference is a rare and legible signal.

**5.4 — SchoolBot.** The only opportunity here with revenue attached.

---

## 6. Revised Architecture

**There is no revised architecture, because there is no product.** That is the finding, not
an evasion.

If §2.3 proceeds, the entire architecture is:

```
Vertex / Gemini SDK call
      ↓  (instrumentation library — the only thing you write)
OTel GenAI spans:  invoke_agent  ·  execute_tool  ·  chat
      ↓  (OTLP, someone else's transport)
Any existing consumer: Promptfoo · Honeycomb · Datadog · Langfuse · Phoenix
```

One package. One job: emit correct `gen_ai.*` spans from Vertex/Gemini and a custom
orchestrator. No primitive, no format, no gate, no diff, no plugin API, no server, no
adapters for anything else. Redaction is a span processor, applied before export, on by
default.

Constraints, stated as invariants so scope creep is visible:
- It **emits**. It does not compare, score, gate, or store.
- It has **no CLI verbs** beyond whatever is needed to verify spans are being produced.
- It pins the developmental `gen_ai.*` conventions explicitly and says so in the README,
  because they have no tagged release.
- If a field can't be determined, it is **absent**, never guessed.

---

## 7. Revised Roadmap

Weeks, not phases. Anything not on this list is out of scope.

| When | Do | Why |
|---|---|---|
| **Day 1** | **Send the G3 disclosure.** GitHub Security Advisory, EvalView SECURITY.md. Wording per CORRECTION 2 in the teardown — the defect is the *asymmetry between PII detection and raw persistence*, not "no PII handling." | Finished work, decaying asset, one email. |
| **Week 1** | Publish the teardown (blog / HN / r/LocalLLaMA). Keep the pre-registration block and both self-corrections in — they are the credibility, not a blemish. Fix the two factual defects in §1.3 before publishing. | Zero marginal cost, real reputational return. |
| **Weeks 2–4** | Instrument SchoolBot with OTel GenAI spans (`invoke_agent`, `execute_tool`, `chat`). Also closes the tracked WAF-bypass item with a proper staging target. | Worth doing for SchoolBot regardless of any AgentGuard decision. Unblocks the frozen reopen trigger. |
| **Week 5** | **The one experiment worth running:** point *Promptfoo's OTLP receiver* at the now-instrumented SchoolBot and re-run E2/E3/E4. This is the path the teardown never tested (§1.2). | Either it works — confirming CONTRIBUTE decisively and cheaply — or it fails on clean trajectory data, which is exactly the frozen reopen condition. Both outcomes are worth one week. |
| **Week 6+** | Founder's call, informed by week 5: either the Vertex OTel instrumentation package (§2.3), or SchoolBot's users, or both. | — |
| **Never** | Plugin API · marketplace · scenario packs · six SDK adapters · `agent-record.json` · replay · hosted anything · the SaaS control plane. | §3. |

Note this roadmap is *compatible with* the frozen pre-registration rather than a
renegotiation of it: week 5 is the second run, gated on the trigger
[`second-run-conditions.md`](second-run-conditions.md) already specifies (OTel
instrumentation present), scoped to E2/E3/E4 as specified, with G1–G4 unchanged. I am not
reopening the verdict; I am scheduling the test that the verdict itself asked for, and
adding the one tool whose real integration path was missed.

---

## 8. OSS Strategy Critique

**Would people contribute? No. And planning for it now is the error.**

The strategy documents model growth on pytest and OpenTelemetry
([`archive/open-source-model.md`](archive/open-source-model.md): "the ecosystem grows the
way pytest and OpenTelemetry grew"). The analogy is backwards in every case:

- **pytest** got its plugin ecosystem *after* becoming the default Python test runner.
  Plugins were the reward for winning, not the mechanism of winning.
- **ESLint / Prettier** are instructive as a *pair*: ESLint won on configurability,
  Prettier won by removing it. Prettier's v1 had zero extension points and one opinion —
  and it is the closer model for a new tool with no users.
- **OpenTelemetry** grew because cloud vendors needed a neutral standard and staffed it.
  It is a consortium outcome, not a solo-maintainer outcome. You cannot bootstrap a
  consortium.
- **Terraform** grew on providers, but only after HashiCorp had already made Terraform the
  default way to touch a cloud — and providers were written by the *clouds*, who had
  revenue reasons.

What actually motivates contributors: **the tool already works for them.** People
contribute adapters to tools they depend on. Nobody contributes an adapter to establish a
dependency. The contribution ladder in
[`archive/open-source-model.md`](archive/open-source-model.md) (scenario author → adapter
author → maintainer → core), the conformance suite, and the four "low-friction contribution
surfaces" are all well designed and all premature: **contribution follows adoption, and
adoption follows one sharp use case.**

There is also an unresolved internal contradiction the founder should see: the same repo
contains "AgentGuard is designed for community contribution from day one"
([`archive/open-source-strategy.md`](archive/open-source-strategy.md)) and "Would people
contribute? No — and planning for it now is the error"
([`archive/final-architecture-review.md`](archive/final-architecture-review.md)), plus two
incompatible plugin taxonomies (`open-source-strategy.md` defines an "Evaluators" plugin
type that `open-source-model.md` doesn't have). Ten further contradictions across the
archived docs are catalogued in the delegated analysis — on the primitive, the buyer, the
moat, the roadmap order, and on whether to build at all. **A design corpus that
contradicts itself on all five load-bearing questions is itself evidence** that the
product was never resolved, only re-described. The archive is correctly named.

**The correct OSS posture, if anything ships:** Prettier's, not pytest's. One opinion, zero
configuration, no extension points, until there are ten external users who asked for one.

---

## 9. Competitor Analysis

Verified against primary sources today (PyPI metadata, GitHub, vendor docs, acquisition
coverage). Adoption numbers are the column the earlier reviews never filled in — and the
column that changes the reading.

| Tool | What it already solves | Adoption | Overlap with the plan | Where it does **not** reach |
|---|---|---|---|---|
| **Promptfoo** (OpenAI, acq. 2026-03-09) | `trajectory:tool-args-match` / `tool-sequence` / `step-count`; **OTLP receiver** (:4318); built-in OpenAI/Anthropic/Bedrock/**Vertex** instrumentation per GenAI semconv; CI gating; JUnit output | Large + OpenAI distribution; remains OSS; folding into OpenAI Frontier | **Total.** This is the whole plan, including the Vertex path the teardown assumed nobody had | Git-committed baselines are not its idiom; opinionated goldens are EvalView's shape |
| **EvalView** | `init`/`snapshot`/`check`; trajectory diff; multi-reference goldens; HTML report; GH Action; cassettes; flakiness scoring (CV, std-dev, CIs) | **~124 stars**, 37 releases since 2025-12-03, `evalview.com`, Cloud planned | **Total on shape** — same three commands, same positioning | Vertex/Gemini (patcher covers OpenAI/Anthropic/Ollama only); **redaction of persisted payloads (G3)**; true in-PR baseline approval |
| **AgentAssay** | SPRT, Fisher/χ²/KS/Mann-Whitney, Wilson/Clopper-Pearson CIs, three-valued PASS/FAIL/**INCONCLUSIVE**; trace-first offline replay; coverage metrics; `vertex_adapter` | **~5 stars**, 7 releases, arXiv:2603.02601 | Owns the statistical core more rigorously than the planned MVP | No git/PR integration; no redaction; research-stage, effectively no community |
| **DeepEval / Confident AI** | pytest-native metrics, span-level scoring, baseline comparison | Large | Assertion + scoring layer | Not a git-diffable pre-merge gate |
| **LangSmith** | Traces, datasets, evals, hosted | Very large | Observability + eval | Closed, hosted, not local-first, not a CI gate |
| **Langfuse / Phoenix / LangWatch** | OSS OTel-native observability; LangWatch adds local/CI scenario tests | Large | Capture + view | Not a merge gate; Phoenix/OpenInference already ship payload hiding |
| **OTel + OpenInference** | The vendor-neutral schema: `invoke_agent`, `execute_tool`, `chat`; `HIDE_INPUTS`/`HIDE_OUTPUTS`; Collector `transform`/`attributes` processors | Datadog v1.37+, Honeycomb, New Relic, Grafana, MLflow, CrewAI, AutoGen | **Ally, and it eats the format layer** — though note: still developmental, dedicated repo, **no tagged releases** | Does not compare, gate, or decide. This is the only genuinely open space, and it is a *feature*, not a product |
| **W&B Weave** | Experiment tracking + LLM traces | Large | Capture + compare runs | ML-experiment idiom, not merge gating |
| **OpenAI Agents SDK / Anthropic SDK** | Built-in tracing and eval hooks | Enormous | Capture at the source | Single-vendor by construction |
| **LangGraph** | Checkpointing, time-travel, `agentevals` | Very large | **Owns replay** | Framework-scoped |
| **CrewAI / Mastra** | Framework-native observability hooks | Large | Capture inside their own runtime | Framework-scoped |

**"Why wouldn't they just add this themselves?" — they already did.** Promptfoo shipped
trajectory assertions and OTLP ingestion before this plan was written. EvalView shipped the
three-command workflow. AgentAssay shipped the statistics. That is not a one-sprint copy
risk; it is a copy that has **already happened**, which is a stronger disqualification than
the one the question anticipates.

**The moat question, answered plainly: there is no moat.** Features are days-to-weeks to
copy. The format has *negative* value against OTel and a name collision with an IETF draft.
Open source is table stakes. Framework-agnosticism is free for everyone once OTel lands.
The noise model plus a calibration corpus is the best candidate and is still only a lead.
The strongest structural candidate in this shape of tooling is a community rule/scenario
registry — and registries need the adoption you don't have, which makes it a consequence of
winning rather than a way to win. Distribution and trust are the real moat in this
category; OpenAI now owns them.

**The honest small-target caveat, stated because it is the strongest argument against my
own conclusion:** if the wall were only EvalView (124 stars) and AgentAssay (5 stars), a
determined solo maintainer with a real production agent could plausibly take this category.
Feature parity with two indie projects is not a closed market. That argument fails on
Promptfoo/OpenAI alone — but it is a real argument, it is the best one available, and the
teardown never made it. The founder should reject BUILD knowing this, not in ignorance of
it.

---

## 10. Final Recommendation

**Uphold CONTRIBUTE. The AgentGuard product line stays closed.** My independent audit of
the verdict found three factual defects in its supporting evidence and every one of them
strengthens the conclusion. The most-likely-wrong claim in the teardown — that no tool can
see a Vertex trajectory — appears false precisely for the tool backed by OpenAI.

**Do these four things, in order:**

1. **Send the G3 disclosure today.** It is drafted, correct, reproduced, and unsent.
2. **Publish the teardown this week**, with §1.3's two factual corrections applied.
3. **Instrument SchoolBot with OTel GenAI spans.** Justified by SchoolBot alone.
4. **Week 5: run Promptfoo's OTLP path against it.** The frozen reopen test, plus the
   tool the teardown missed. If the incumbents work on clean trajectory data, CONTRIBUTE
   is permanent and you close the file with data. If they fail, the pre-registration —
   not a feeling, and not this document — reopens BUILD.

**Then choose between two honest paths**, and the choice turns on what you want, which is
not mine to decide:

- **Want an OSS calling card?** Ship the Vertex/Gemini OTel GenAI instrumentation package.
  Narrow, standards-aligned, nobody's roadmap, genuinely useful. Low star ceiling, no
  revenue.
- **Want a business?** SchoolBot. You have deployed users. The tooling category is
  contested by OpenAI; "AI product with real users" is contested by nobody.

**Would I install AgentGuard as specified? No.** Not because it's badly built — the
engineering in this repo is above average and the reasoning discipline is well above
average. I wouldn't install it because on the day I needed it I would `pip install
promptfoo`, get trajectory assertions and an OTLP receiver maintained by OpenAI, and never
learn AgentGuard existed. The command that *would* convince me is
`pip install agentguard-vertex && agentguard-vertex verify`, printing correct
`gen_ai.*` spans from my Gemini multi-agent app that Promptfoo and Honeycomb then consume
unmodified — because on that day, nothing else on the list works and I have a production
agent I cannot see. The output that would make me uninstall in ten seconds is a green
`✅ SECURE` on an agent nobody instrumented, or a `⚠️ REGRESSION DETECTED` on an unchanged
agent — which is, precisely and instructively, what EvalView printed on its first run.

---

### Gate status

**Council gate 1 (independent research before drafting): complete.** `web_lookup`
(Gemini) ran before this document was drafted, deliberately framed as neutral market
questions rather than "critique my plan," so the research was not anchored on my framing.
Its findings were then validated against primary sources: PyPI JSON metadata for both
competitors' release histories was fetched directly, and both packages' existence and
version numbers were independently confirmed — the tombstone's competitors are **real, not
hallucinated**, which was the first thing I checked and the thing that would have
invalidated everything had it failed. `analyze_files` (Gemini) performed the cross-document
contradiction analysis in §8.

**Council gate 2 (`adversarial_review`): not applicable — no PR, no diff.** This document
is itself the adversarial pass, and it argues against the position that commissioned it.
Nothing in the working tree was modified; the only new file is this review.

**Authority:** this is a recommendation. The founder decides. The frozen reopen criteria in
[`second-run-conditions.md`](second-run-conditions.md) remain the only legitimate route
back to BUILD, and this review does not attempt to renegotiate them.
