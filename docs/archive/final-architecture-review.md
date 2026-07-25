# Product Reality Review v3

**Subject:** AgentGuard (working codename) — "open-source developer toolkit for capturing, comparing, testing and understanding AI agent behavior"
**Date:** 2026-07-25
**Reviewer stance:** OSS maintainer / AI infra architect / startup CTO. Adversarial by assignment.
**Reviewed:** the v3 brief, the Phase-1 README and roadmap, the "Agent Run Record" format draft, the CONTRIBUTING draft, and the prior reframing message (security scanner → agent security platform → workflow platform). Plus a live market check, because a design review that only reads your own documents is worthless.

**Standing instruction honored:** I assumed every prior decision could be wrong. Several are.

---

## 1. Executive Summary

The problem you picked is real. The framing is defensible. The design is competent.

And the project, as currently specified, should not be built — because **it already exists, shipped, under at least two names, and one of your named competitors shipped the differentiating feature four months ago.**

Three findings, in order of severity.

### Finding 1 — The idea is occupied, not open (fatal as specified)

There is an open-source Python tool called **EvalView** whose pitch is, verbatim, snapshot your agent's behavior and then diff every subsequent run against it — "think of it like `git diff` for agent behavior," and elsewhere "like Jest snapshots, but for tool-calling, multi-turn agents." Its CLI is `evalview init` / `snapshot` / `check`. It diffs the whole trajectory — tool names, parameters, order — deterministically and offline with no API key, with an optional LLM-judge layer on top. It ships a GitHub Action, a `--fail-on REGRESSION` non-zero exit for CI, HTML reports, a `watch` mode, and a documented answer to nondeterminism (multi-reference goldens: up to five acceptable baselines, pass if any match). Its README explicitly positions itself as a merge-time regression gate as distinct from observability (Langfuse/LangSmith) and metric scoring (promptfoo/DeepEval/Braintrust).

That is your product. Not adjacent to it. It is the same product, the same command shape, the same three-line quickstart, the same competitive positioning paragraph, and the same "snapshot then diff" primitive. It is on PyPI, on GitHub Marketplace, and has its own domain.

It is not alone. `tool-call-diff` and `agentsnap` are smaller published tools doing the diff-two-runs job. LangChain ships `agentevals` for trajectory evaluation. **AgentAssay** is a published framework (arXiv:2603.02601) doing statistical verification of nondeterministic agent workflows via behavioral fingerprinting — which is the version of this idea with actual research underneath it. LangWatch is OTel-native with local/CI scenario tests.

**And Promptfoo — the competitor you asked me to compare against — already shipped trajectory assertions.** `trajectory:tool-used`, `trajectory:tool-args-match`, `trajectory:tool-sequence`, `trajectory:goal-success`. It ingests OTLP, instruments its providers per the OTel GenAI semantic conventions, normalizes framework-specific span attributes into a common tool shape, and has had a CI GitHub Action for years. Your Section 2 question — "why wouldn't those projects simply add this feature themselves?" — has an empirical answer: **they did, before you asked.** And Promptfoo is now inside OpenAI (acquisition announced 2026-03-09, OSS continuing, technology folding into OpenAI Frontier), which means the incumbent in your category now has a frontier lab's distribution behind it.

If you had shipped this in mid-2025, you'd have been early. In July 2026 you are late to a crowded, consolidating category, and your differentiator is a feature in someone else's changelog.

### Finding 2 — Phase 1 solves nondeterminism by deleting it (fatal as designed)

Your Phase-1 design principles include **"Simulate, don't execute"** — recording never calls a real API — and **"Deterministic: same agent, same inputs, same seed → same record,"** with `"model": "simulated"` in the sample record.

Follow that through. If the model is simulated and the tools are observed pure functions under a fixed seed, then the run record is a deterministic function of your source code. Which means `agentguard diff` can only ever report a change when **you changed the code** — and in that case `git diff` already told you, for free, more precisely, ten seconds earlier.

The entire stated reason this product exists is the class of change git *cannot* show you: a provider silently reweights a model, a one-line prompt edit changes tool selection, retrieval drifts. Your architecture makes that class of change structurally unobservable. You have built a beautifully engineered instrument that is blind to the only phenomenon it was built to detect.

This is not a bug to fix later. It is the load-bearing decision, and it is inverted. "Zero dependencies," "no magic auto-detection," and "deterministic" are the aesthetic values of a great systems tool — they are also, in this specific combination, an elaborate way of avoiding the hard problem. The hard problem *is* the product. Everything else is CLI plumbing that a competent engineer writes in a weekend.

### Finding 3 — There is no moat, and the primitive is not a primitive

Full treatment in §6 and §9. Summary:

- `agent-record.json` fails **your own test**. You asked: if the file disappeared, would the platform still exist? Yes — swap in OTel spans, JSONL, SQLite, Parquet, anything. Snapshot/diff/test all survive. By your criterion, stated in your own brief, **the primitive is wrong.** It is a serialization format, and serialization formats are the cheapest layer in any system.
- The format cannot become a community standard, and the attempt is actively harmful to adoption. OpenTelemetry graduated CNCF on 2026-05-21; GenAI semantic conventions at v1.41 already define agent, workflow, tool and model spans plus MCP tracing, with Datadog, Grafana, Honeycomb, Langfuse, LangSmith, Phoenix, LangWatch and Promptfoo consuming them. Every one of your named competitors bet on that schema. A new hand-rolled JSON envelope from an unknown maintainer is not a standard; it is an import step someone has to write.
- No credible moat exists on the current plan. Not features, not open source, not "we're framework-agnostic."

### Verdict

**Do not build the platform. Do not build the toolkit. Do not build `agent-record.json`.**

There is one narrow, defensible, genuinely unserved position left in this space, and it is not the one in your documents. It is in §5 and §10. It requires giving up the word "platform" permanently and giving up the format entirely.

---

## 1.5 Product Validation (answers to brief §1)

**1. What problem does this actually solve?**
As written: "I changed something and I can't tell whether my agent still behaves correctly." As *built* (simulated, seeded, deterministic): nothing that `git diff` and `pytest` don't already solve. Two different answers to the same question is itself the diagnosis — the docs describe one product and the code implements another.

**2. Is the problem painful enough that developers actively search for a solution?**
Yes, and this is the strongest thing about the project. The evidence is unambiguous: silent behavioral regression is the recognized hard problem of agent engineering in 2026 — same input, different tool sequence, HTTP 200, wrong behavior, tests still green. Multiple independent tools, at least one peer-reviewed framework, a comparison-content industry, and every observability vendor's marketing page all point at it.

But read that evidence again. **Demand this legible is demand that has already been supplied.** "Developers actively search for this" and "there are five tools on page one of that search" are the same sentence. Validated demand is not an opening; it is a competition you are entering four months late without distribution.

**3. Which developer installs this TODAY? Pick one.**

**Primary persona: the sole owner of a production agent that performs irreversible actions, at a 5–50 person company, with no eval infrastructure and a model-version upgrade due.** Concretely: one engineer, owns the refund/payout/booking/write-to-database agent, has a `tests/` directory containing only unit tests for the tool functions, and is personally afraid of the next provider deprecation notice. She has budget authority of zero and `pip install` authority of total. She'll adopt anything that runs in CI, requires no server, and produces a red line she can paste into a PR.

Why her: she has the fear (irreversible actions), the authority (none needed), the trigger event (forced model migration), and no incumbent (too small for LangSmith seats, too busy to have written evals). She is also the only persona for whom "behavior changed" is *itself* the alarm — for everyone else, "did quality drop" is the real question, which is a scoring problem, not a diffing problem, and scoring is where the incumbents are strong.

Rejections:
- **Enterprise platform engineer** — buys, doesn't `pip install`. Needs SSO, SOC 2, an MSA, a vendor that will exist in three years. You are none of those. Also already consolidated on Datadog or LangSmith; "one more pane" loses to "one fewer pane" every time.
- **OSS maintainer / framework author** — they are your competition, not your users. LangChain ships `agentevals`; LangGraph has checkpointing and time-travel; every SDK ships tracing. Frameworks do not adopt third-party dependencies that overlap their own roadmap.
- **Solo hobbyist** — no CI, no baseline discipline, no regressions worth catching, and the highest support-to-value ratio of any user class. Will give you a star and an issue titled "doesn't work" with no traceback.
- **Research engineer** — has a bespoke harness, measures against benchmarks not baselines, and needs statistical significance rather than diffs. AgentAssay is aimed here and has publication credibility you cannot match.

**4. Stars or enterprise sales?**
Stars, and that's the trap. The category is star-friendly — the terminal diff `lookup_order → check_policy → process_refund` becoming `… → escalate_to_human` is an excellent screenshot, and "Jest snapshots for AI agents" is an excellent tweet. You could plausibly get 500–2,000 stars on a good launch day.

None of which is adoption. Star-optimized dev tools in a crowded category converge on the same outcome: a spike, a dozen `init` runs, two issues, and a repo that looks alive for six weeks. The metric that matters is **second-week retention of `check` in someone else's CI**, and nothing in the current plan is designed for it. Meanwhile the monetizable version of this — baseline hosting, team review, audit trails — is enterprise-shaped, and EvalView has already started down that path (cloud baseline sync). Pick one motion honestly; the current design straddles.

---

## 2. What Survives

Small list. That is the point.

1. **The core observation.** Agents change behavior without their code changing, and the industry has no default gate for it. This is correct and it is the only asset with real value.
2. **The gate framing.** "Regression gate at merge time" ≠ observability ≠ scoring. Correct, sharp, and — importantly — already the positioning paragraph of your closest competitor, which is confirmation that the framing is right and that you don't own it.
3. **CI-first, exit-code-shaped, no server, no signup.** Right instinct. Non-negotiable. Keep it.
4. **Security demoted to a scenario pack.** Correct, and the one place your documents and your instincts fully agree. Security as a *consumer* of the mechanism, never the mechanism.
5. **Explicit `schema_version` from commit one.** Right call for entirely different reasons than you think — not because the format is a standard, but because it isn't, so you'll break it often.
6. **The `@tool()` decorator over auto-detection.** "False confidence is worse than no detection" is a genuinely good engineering value. Keep the value; §7 argues the decorator is the wrong place to spend it.

---

## 3. What Dies

Everything below goes. Not "later." Now, in the docs, today.

- **`agent-record.json` as platform primitive, as product identity, and as standards ambition.** Demote to an unadvertised internal cache detail. Delete the words "core primitive" and "everything revolves around this artifact." No format-spec doc, no versioned public schema page, no "become a standard" language. Consume OTel GenAI spans (§7).
- **"Platform," "toolkit," "ecosystem."** All three are words for "I have not chosen." The brief lists nine consumers (snapshot, diff, scenario testing, reporting, plugins, security, quality, cost, reliability). Nine consumers, zero users.
- **"Simulate, don't execute."** This is Finding 2. It must die or the product is inert. Replace with record/replay of *real* provider and tool traffic — cassettes, VCR-style. Real calls once, replayed free forever. That preserves the determinism you correctly want while restoring the nondeterminism you need to observe.
- **Replay (Phase 2 as written).** LangGraph already has checkpointing and time-travel; frameworks own their own replay because replay needs framework-internal state. You will lose this on the merits. The *useful* subset — replaying cached model/tool responses so CI is fast and free — is not "replay," it's caching, and it belongs in the core loop, not Phase 2.
- **Plugin architecture, marketplace, community scenario hub, report-format extensibility.** You are designing an extension API for zero extensions (§8).
- **Level-2 SDK integrations for OpenAI / Anthropic / LangChain / LangGraph / CrewAI / Mastra.** Six adapters is a permanent maintenance tax paid by one person against six teams shipping breaking changes on their own schedules. This is how solo OSS projects die — not abandoned, just perpetually two versions behind.
- **`agentguard show` / `list`.** Nobody installed a tool to browse JSON. If the diff is good these are unnecessary; if the diff is bad these don't save it.
- **The name.** Already flagged in your own draft and still true: multiple GitHub orgs ship AI-agent security tooling called AgentGuard, at least one adjacent product claims trademark on a near-identical name, and "Guard" advertises the security positioning you deliberately abandoned. It is a codename. Replace it before the first public commit — one word, no "agent," no "guard," no "AI."

**Smallest product people would still love:** one command that runs my real agent against a handful of recorded scenarios, N times, and tells me in CI whether its behavior changed in a way that isn't noise — with the diff readable in the PR without clicking anything. That is `init`, `snapshot`, `check`. Three commands. Everything else in every document you have written is deletable.

And to be blunt: **that product exists and is called EvalView.** Which is why §5 and §10 are the actual review.

---

## 4. Biggest Risks

Ranked by probability × damage.

1. **Duplicate-and-lose (≈certain, as specified).** Ship this and the first Hacker News comment is a link to EvalView. There is no recovery from being the second, less-mature implementation of a tool with the same three commands.
2. **The determinism inversion (≈certain, unless Finding 2 is fixed).** A gate that cannot fire is worse than no gate: it manufactures false confidence, which is the exact failure mode your own design principles claim to reject.
3. **The noise problem eats you (high).** Once you *do* execute real models, every run differs. Diff without a noise model produces a permanently red CI, and permanently red CI gets deleted from the workflow file within one week. Multi-reference goldens (up to 5 accepted variants) is EvalView's answer; it's a workable heuristic, not a solution. Nobody has solved this well. **This is where the actual product is** (§5, §8).
4. **CI cost and latency (high, underrated).** Real agent runs × N repetitions × M scenarios × every PR = minutes and dollars per push. Teams silently drop expensive CI steps. Without response caching this is unadoptable at any quality level, and it is absent from every document you have written.
5. **Records contain customer data (high, blocking).** A trajectory captures prompts, tool arguments, retrieved documents. Committing baselines to git means committing PII. OTel's own guidance treats payload capture as opt-in and recommends external storage with span references, precisely for this reason. No redaction story = no adoption at any company with a compliance function = your entire persona.
6. **Solo-maintainer capacity vs. six adapters (high).** You have a full-time engineering job with an active sprint load. Six framework integrations plus a plugin API plus a scenario hub is a team's roadmap.
7. **Format lock-in against a graduated CNCF standard (medium-high).** Competing with OTel GenAI semconv is a losing bet on a five-year timescale, and being OTel-native is free adoption of every existing instrumentation library.
8. **Naming/trademark collision (medium probability, cheap to avoid, expensive to ignore).**

---

## 5. Biggest Opportunities

This is the constructive half. Four real gaps, ranked. They are what should be in the brief instead of "plugins" and "marketplace."

### Opportunity A — Own the noise model. This is the only real product.

Every tool in this category punts on the central question: **given two runs of a nondeterministic agent, which differences are meaningful?** The current state of the art is "save up to five acceptable variants and pass if any match." That is a shrug with a UI.

The rigorous version is statistical: run N times, build a distribution over trajectory shapes, and report a change only when the new distribution differs from the baseline distribution beyond a calibrated threshold. Report *rates*, not diffs: "`verify_identity` was called in 5/5 baseline runs and 2/5 candidate runs — p < 0.05." Distinguish flaky-from-day-one from newly-flaky. Auto-quarantine unstable scenarios instead of failing them. Learn the noise floor per-scenario during `init` rather than asking the user to configure thresholds.

That is a hard, tasteful, empirical problem. It is the one thing here that cannot be copied in a sprint, because copying it requires the calibration corpus and the judgment about what counts as a difference — accumulated, not cloned. AgentAssay is the closest competitor and it is a research framework, not a tool a tired engineer runs at 6pm. **The gap between "peer-reviewed methodology" and "three commands and a red line in a PR" is the only opening in this market.**

Everything else in your documents is UI on top of this. If you build only this, you have a product. If you build everything else and not this, you have a duplicate.

### Opportunity B — Make CI free. Cassettes over simulation.

Record real provider and tool traffic once; replay it deterministically forever. Same determinism your Phase 1 wanted, achieved honestly. Cheap CI, offline CI, reproducible CI, and — crucially — a genuine answer to the model-upgrade question: replay the *same recorded user inputs* against the *new model* while tool responses stay fixed, isolating the model as the single variable. That experiment is what your persona actually wants to run, and no tool in the category makes it a one-liner.

### Opportunity C — Baseline review as a human workflow, not a file.

The unsolved UX question in snapshot testing is not capture or comparison. It's **approval**: who decides the new behavior is correct, where does that decision live, how does it survive review. Jest's `-u` is a blunt instrument and everyone knows it. A behavior diff rendered in a PR comment, approvable by a reviewer, with the baseline update as a commit in that same PR, is a workflow no one owns yet — and workflow habits are stickier than any file format. This is also the only credible commercial surface, if you ever want one.

### Opportunity D — Redaction as a first-class feature, not a footnote.

Field-level redaction, hashed-value comparison (compare that an argument changed without storing what it was), local-only default with explicit opt-in for anything that leaves the machine. Ship it in v0.1 and say so on line four of the README. This is the thing that turns "interesting" into "allowed."

### Missing foundations (answers to brief §5)

Beyond A–D, absent from every document: semantic comparison of two different-but-equivalent natural-language outputs (and the fact that your judge is itself nondeterministic and needs its own baseline); baseline storage and provenance (which commit, which model version, which prompt hash produced this baseline — a baseline without that metadata is uninterpretable within a month); environment/side-effect fakes for tools that write; multi-turn and stateful sessions; and a defined semantics for "meaningful change" that a user can read in one paragraph. That last one is the real spec, and it does not exist yet in any document.

---

## 6. Revised Architecture

### On the primitive (answers to brief §3)

Fundamental or convenient? **Convenient.** Your own disappearance test settles it, and the comparisons you asked for confirm it:

| Artifact | Why it's actually load-bearing | Lesson |
|---|---|---|
| Git commit | Content-addressed; identity *is* the hash. Remove the object model and git ceases to exist. | A real primitive is definitional, not serial. |
| OTel trace | Standardized by a CNCF-graduated body with vendor co-investment; value is the shared vocabulary across dozens of producers and consumers. | Standards come from consortia or from dominance. |
| JUnit XML | Became universal *because JUnit won first*. The format was a byproduct. | Tool first, format later. |
| SARIF | OASIS standard, driven by Microsoft/GitHub with a distribution channel attached. | Standards need a channel. |
| Terraform plan | HashiCorp's dominance made it interoperable. Also: the plan's value is the *diff semantics*, not the file. | The comparison is the product. |
| OpenAPI | Community standard because the schema *is* the deliverable for humans and machines both. | Not analogous to a run log. |

Your artifact is a run log. Run logs are the most commoditized data structure in this entire space and OTel already defines the vendor-neutral version. **Can `agent-record.json` become a community standard? No.** Not because the design is bad — because standards require either institutional weight or prior dominance, and you have neither. Pursuing it costs you the free adoption that OTel-native ingestion would give you.

**The real primitive is the comparison function**, plus its noise model: the canonicalization rules, the equivalence classes, the statistical threshold that decides what a change *is*. That is definitional — remove it and there is no product, only a JSON file. Note what this implies: the primitive is a *judgment*, not an artifact. That's uncomfortable for an infra-minded engineer, and it's the correct answer.

### Revised shape

```
 real agent (unchanged, no decorators)
        │  emits OTel GenAI spans via existing instrumentation
        ▼
   ingest ──► canonicalize ──► N-run distribution ──► compare vs baseline
        │                                                     │
    cassette cache (replay: free, offline, deterministic)      ▼
                                                    PR-readable verdict
                                                    exit code 0/1
```

Four components. One integration surface (OTel). One artifact, unadvertised. Zero plugin APIs.

### Framework strategy (answers to brief §7)

Your three levels are one level too many and five adapters too heavy. Level 2 is the part that kills solo projects.

**Better abstraction: OTel GenAI spans are the adapter.** OpenInference, OpenLLMetry, and vendor SDK instrumentation already cover OpenAI, Anthropic, LangChain, LangGraph, CrewAI, LlamaIndex, Bedrock, MCP tool calls and more. If you ingest OTLP, you inherit all of it and you maintain none of it — which is precisely what Promptfoo did, and it's the correct call. Keep exactly one hand-written fallback: a context manager for people not instrumented yet.

Two levels, one of which someone else maintains. That is the whole framework strategy, and it removes the largest single risk item on your roadmap.

---

## 7. Revised Roadmap

Your order — Snapshot → Diff → Scenario Engine → Replay → Community → Security — is wrong in two places. Replay is a framework's job. Community-before-adoption is backwards. And the hard part (noise) is nowhere in the list.

Design backwards from the artifact that decides adoption: **the sentence in a PR that makes an engineer trust the tool.** Something like:

> `refund_flow` — `verify_identity` called in 5/5 baseline runs, 2/5 candidate runs (p=0.03). Model changed: `claude-opus-4-8` → `claude-opus-5`. Tool responses replayed from cassette. Non-determinism: baseline stable across 5 runs.

Every piece of that sentence is a requirement. Build them in this order:

| # | Milestone | Why here | Weeks |
|---|---|---|---|
| 0 | **Kill/confirm decision.** Install EvalView, AgentAssay, `agentevals`, Promptfoo trajectory assertions. Run all four against SchoolBot. Write one page: what breaks, what's missing, what a tired engineer hates. | If nothing breaks, stop and contribute to one of them instead. This is the highest-EV week of the project and it is not in any document you have written. | 1 |
| 1 | **Ingest + canonicalize.** OTLP GenAI spans → normalized trajectory. Redaction in from day one. | Foundation, and free coverage of every framework. | 2 |
| 2 | **N-run distribution + noise floor.** Run scenarios N times, learn per-scenario stability, quarantine unstable ones. | **The product.** Before diff, because diff without this is noise. | 3 |
| 3 | **Statistical compare + the verdict line.** Rates not diffs. Exit code. `--json`. | First moment a human feels value. | 2 |
| 4 | **Cassettes.** Record once, replay free. Model-swap-only mode. | Makes CI adoptable and enables the upgrade experiment. | 2 |
| 5 | **PR comment + approve-the-new-baseline flow.** | Turns a tool into a habit. | 2 |
| 6 | **Dogfood publicly.** SchoolBot's agents in CI, badge, real failures in the changelog. | Credibility. You have a real multi-agent system; almost no competitor's author does. | ongoing |
| — | Security pack, scenario packs, plugin API, hosted anything | After ≥10 external CI users. Not before. | later |

Roughly 12 focused weeks — your three-month budget — and it ends with something narrower and sharper than the current plan ends with, which is nine half-features.

---

## 8. OSS Strategy Critique (answers to brief §6)

**Would people contribute? No — and planning for it now is the error.**

The CONTRIBUTING draft says the project should grow like pytest plugins or ESLint rules. Look at what actually happened in those projects:

- **pytest** — plugins arrived *after* it was the default Python test runner. Contribution was the reward for winning, not the strategy.
- **ESLint** — rules arrived after linting was already a habit and the rule interface was the smallest possible unit of work with immediate personal payoff.
- **Prettier** — grew enormously with an almost hostile contribution surface. Its strategy was the *opposite*: remove options, remove decisions, be aggressively opinionated. Nearest analogue to what you should do.
- **OpenTelemetry** — grew because competing vendors funded engineers to work on it, since a neutral standard was cheaper than N proprietary integrations. Unavailable to you.
- **Terraform** — providers were written by *vendors seeking distribution* through Terraform's user base. Also unavailable: you have no user base to distribute.

The pattern is uniform. **Contribution follows adoption, and adoption follows a single sharp use case.** Designing a plugin API for a tool with zero users is cargo-culting the visible artifacts of successful projects while skipping the invisible cause.

What contributors respond to, in order: their bug got fixed today; the maintainer replied in hours; the smallest useful contribution is fifteen minutes of work; their name is visible. None of that requires a plugin architecture. All of it requires a maintainer with time — which is exactly what six framework adapters would consume.

**Adopt the Prettier model for v1:** zero configuration, one opinion, no extension points, ruthless about scope. Revisit extensibility if and only if strangers are running `check` in CI and asking for it.

One more thing, unwelcome but true: **the OSS strategy that maximizes success probability here may be to contribute to EvalView or AgentAssay instead of competing.** Opportunities A–D are all missing from EvalView, all valuable, and all shippable as PRs into a project that already has the distribution, the domain, and the Marketplace listing. Sole ownership of a duplicate is worth less than co-ownership of the winner. That is a real option and you should price it honestly before writing a line of code.

---

## 9. Competitor Analysis (answers to brief §2 and §8)

| Project | Solves today | Overlaps you | Doesn't do | Copy cost |
|---|---|---|---|---|
| **Promptfoo** (now OpenAI) | Config-driven evals + red-teaming, CI Action, OTLP ingest, **`trajectory:tool-used` / `tool-args-match` / `tool-sequence` / `goal-success`** | Nearly total on trajectory assertion + CI gating | Auto-baseline capture without written assertions; statistical noise modeling; cassettes | **Already shipped.** Snapshot-baseline mode is one sprint. |
| **EvalView** | `init`/`snapshot`/`check`, full trajectory diff offline, multi-reference goldens, HTML report, GH Action, cloud baseline sync | **Total. This is your product.** | Statistical noise model; cassette replay; PR approval workflow; redaction | N/A — they're ahead |
| **AgentAssay** | Peer-reviewed statistical verification of nondeterministic agent workflows; behavioral fingerprinting | Direct on Opportunity A, the good part | Ergonomics; three-command UX; CI-native feel | Hard for them to lose on rigor, easy to lose on UX |
| **DeepEval / Confident AI** | pytest-native metrics, span-level scoring, baseline comparison, calibrated release gates | High on CI gating and baselines | Assertion-free auto-baselining; noise distributions | One sprint |
| **LangSmith** | Traces, datasets, evals, hosted, closed | Overlaps the eval loop | OSS, local-first, no-signup, CI-first ergonomics | Won't bother; different motion |
| **Langfuse / Phoenix / LangWatch** | OSS observability, OTel-native, self-hostable; LangWatch adds local/CI scenario tests | Growing on the gate | Merge-time gate as primary product | One sprint each |
| **OTel + OpenInference** | The schema and transport; CNCF-graduated; agent/tool/workflow/MCP spans | Owns your "primitive" | Any opinion on comparison, thresholds, or pass/fail | Won't — out of scope. **Ally, not competitor.** |
| **W&B Weave** | Experiment tracking + LLM traces | Comparison across runs | CI gate; local-first | Won't prioritize |
| **OpenAI Agents SDK / Anthropic SDK** | Built-in tracing, eval hooks; OpenAI now owns Promptfoo | Bundling risk | Cross-vendor neutrality | Bundling is their default move |
| **LangGraph** | Checkpointing, time-travel, `agentevals` | **Owns replay** | Cross-framework gating | Already done |
| **CrewAI / Mastra** | Frameworks with own observability hooks | Adapter surface | Neutral gating | Won't bother |

**Why wouldn't they add this themselves?** They already have. That is the finding. The residue that isn't yet commoditized is Opportunities A–D, and even those are one focused sprint away for any funded team that decides they matter.

### The moat (brief §8)

**There is no moat. Say it plainly.**

Candidates, assessed honestly:
- *Features* — no. Days to weeks to copy.
- *The format* — no. Negative value against OTel.
- *Open source* — no. Everyone is.
- *Framework-agnostic* — no. OTel makes it free for everyone.
- *Noise model + calibration corpus* — the best candidate, and still only a **lead**, not a moat. Judgment about what counts as a meaningful change accumulates from real usage and is genuinely annoying to clone. Months of lead, not years.
- *A community rule/scenario registry* — the strongest structural moat in this shape of tooling (Semgrep's real asset is its rule registry, not its engine; ESLint's is its rule ecosystem). But registries are a *consequence* of adoption. You cannot start there.
- *Distribution and trust* — the actual moat in this category, and the one you don't have.

So the honest strategic statement is: **this is a race, not a fortress.** The winning conditions are taste, speed, dogfooding credibility, and maintainer responsiveness — sustained over a year, part-time, against funded teams and an OpenAI-owned incumbent. That is a legitimate bet, and it is a very different bet from the one the current documents describe. Make it with your eyes open or don't make it.

---

## 10. Final Recommendation

### The narrative, if you proceed (brief §9)

**One sentence:** Your agent's behavior changes when you didn't change your code — this tells you, in CI, with statistics instead of vibes.

**One paragraph:** Agents aren't deterministic, so the usual test isn't available: run it twice and you get two answers, both plausible. Existing tools either watch production after the fact or ask you to write down in advance what "good" looks like. This runs your real agent N times against recorded scenarios, learns which parts of its behavior are stable and which are noise, and then fails your build only when the *distribution* of its behavior actually moves — with tool and model responses replayed from cache, so it costs nothing and runs offline.

**Elevator pitch:** Snapshot testing doesn't work for agents, because every run is different. So we do the statistical version: N runs, a noise floor per scenario, and a verdict that reads *"`verify_identity` dropped from 5/5 runs to 2/5"* instead of a wall of JSON. Three commands, no server, no signup, and cassette replay so CI is free.

**What developers immediately think:** *"How do you diff nondeterministic output?"* — every single one, within four seconds. Answer it in the third line of the README or lose them. Then: *"Is this observability or testing?"* (testing — say it explicitly), *"Do I need a server?"* (no — say it louder), *"How much does CI cost?"* (nothing after the first record — lead with it).
**What excites them:** gating a model upgrade; the verdict line; zero assertions to write.
**What confuses them:** where baselines live, who approves changes, and whether their prompts are leaving the machine.

### Would I install it? (brief §11)

Today, as specified: **no.** The README's "simulate, don't execute" tells me it can't detect the thing I'm worried about, and thirty seconds of searching finds a more mature tool with the same three commands.

With the revised architecture: **yes, on one condition** — `pip install X && X init && X check` produces a meaningful red or green against my real agent in under five minutes with no API key, no config file, and no account.

**Output that would make me smile:** the verdict line above. Specifically `2/5` rather than a diff, `p=0.03` rather than an emoji, and a note that the model version changed underneath me.
**Output that would make me uninstall in under a minute:** a wall of JSON; a red build I can't reproduce locally; a green build after I deliberately broke the prompt; different results on two consecutive unchanged runs; a request for an API key before the first result; a surprise judge-model bill; celebratory streak counters where a stack trace should be.

### What to actually do

1. **Spend week one trying to kill the project.** Install EvalView, AgentAssay, `agentevals`, and Promptfoo's trajectory assertions. Run every one against SchoolBot's real agents. Document precisely what fails. This is a one-week option on not wasting three months, and it is the single highest-value action available to you.
2. **Then choose one of three, explicitly, in writing:**
   - **(a) Contribute.** Take Opportunities A–D into EvalView or AgentAssay as PRs. Lowest risk, real impact, no moat, no ownership. Genuinely the highest expected value if week one shows those tools are basically fine.
   - **(b) Build the narrow thing.** Statistical noise modeling + cassettes + PR approval flow, OTel-native, three commands, new name. Ship in 12 weeks. Race, not fortress. Do this only if week one surfaces failures you can articulate in one sentence.
   - **(c) Don't.** Your Farmer1st work is producing genuine, scarce expertise in money-touching agent reliability. Vertical reliability infrastructure for irreversible-action agents is a narrower and less contested position than horizontal agent testing, and the domain knowledge behind it is much harder to copy than a diff algorithm. That may simply be the better project.
3. **If (b): delete the platform documents first.** The nine-consumer architecture, the format spec, the plugin API, the marketplace, the six adapters, the replay phase. They represent real work, and keeping them will quietly pull scope back to nine half-features. Write the one-paragraph scope statement, put it at the top of the repo, and treat it as immutable for twelve weeks.
4. **Rename before the first public commit.**

### Closing

The instinct that led you here is good: you identified the correct hard problem in agent engineering roughly a year before most teams will feel it, and you correctly demoted security from headline to plugin.

What went wrong is a pattern worth naming, because it will recur. Twice now the project has expanded in scope in response to uncertainty — scanner → platform → toolkit — and each expansion moved further from a testable claim. And the one design decision that would have forced the hard question ("what happens when I execute the real model twice and get two answers?") was resolved in the direction that made it disappear. Scope growth and difficulty avoidance are the same reflex wearing different clothes.

The version of this project with a real chance is smaller, harder, and less impressive-sounding than anything in the current documents: **learn what noise looks like, then report only what isn't noise.** One difficult idea, executed well, against a real agent you already run in production.

That is a project. The platform is not.

---

### References

Market check performed 2026-07-25.

- EvalView — https://github.com/hidai25/eval-view · https://evalview.com/ · https://pypi.org/project/evalview/ · https://github.com/marketplace/actions/evalview-ai-agent-testing
- AgentAssay — arXiv:2603.02601; discussion: https://codex.danielvaughan.com/2026/06/27/agentassay-regression-testing-non-deterministic-codex-cli-agent-workflows-behavioral-fingerprinting/
- Promptfoo trajectory assertions & OTLP tracing — https://www.promptfoo.dev/docs/tracing/ · https://www.promptfoo.dev/docs/guides/evaluate-openai-agents-python/ · OpenAI acquisition announced 2026-03-09
- OpenTelemetry GenAI semantic conventions v1.41 (Development status); OTel CNCF graduation 2026-05-21 — https://greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions · https://www.webhani.com/blog/opentelemetry-graduation-genai-observability-2026
- `tool-call-diff` / `agentsnap` — https://github.com/MukundaKatta/tool-call-diff
- Category landscape — https://dev.to/thedailyagent/5-open-source-tools-for-testing-ai-agents-before-they-break-production-5d9c · https://www.confident-ai.com/knowledge-base/compare/best-llm-evaluation-tools-for-ai-agents
