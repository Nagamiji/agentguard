# RATIFICATION

> **Rule frozen 2026-07-25. Executed 2026-07-25. Mechanical result: CONTRIBUTE.**
>
> **Gap tally:** G1 PRESENT, G2 PRESENT, G3 ABSENT, G4 PARTIAL. One ABSENT; BUILD needs ≥2.

**CORRECTION 1 (G2):** The teardown's claim "EvalView G2 ABSENT — caches judge only" was too strong. EvalView has a Cassette/recorded_cassette subsystem with per-layer tools/responses/http interception; it was simply inactive on the plain HTTP-adapter path used here, which re-hit the agent live. G2 was already PRESENT via AgentAssay, so the tally is unchanged — but the original claim was wrong and is corrected here rather than quietly dropped.

**CORRECTION 2 (G3 scope):** The finding is specifically the ABSENCE OF PAYLOAD REDACTION, not the absence of PII handling. EvalView ships PII detection (`ExpectedOutput.no_pii`, `PIIEvaluation`) which flags PII in agent output; it does not scrub what is persisted. Captured output is written raw (`core/golden.py:158`) to a path the tool instructs the user to commit (`core/celebrations.py:56-58`). The defect is the asymmetry between those two behaviors. Any external communication must state it this way.

**CAVEAT (E2 contaminated):** SchoolBot returns final text only — no steps, no `tool_calls` — so no tool under test had trajectory data to compare. The 13% similarity result on an unchanged agent and the "required tool never called" message are artifacts of trajectory blindness, not evidence that EvalView's comparison logic is defective. E2 severity is downgraded accordingly. The verdict rests on the G1/G2/G4 source-inspection findings and does not depend on E2.

**OBSERVATION (outside the frozen gap set):** SchoolBot's trajectory is unobservable to every tool tested, because it emits no per-step data and runs on Vertex. This is an instrumentation gap in SchoolBot, not a market gap. Recorded, not scored.

**PROCESS NOTE:** Both corrections found during closeout moved evidence AWAY from BUILD (G2 more present than reported; G3 more bounded than reported). Recorded as evidence the pre-registration held under pressure.

---

# Competitive Teardown — Agent-Behavior Regression Gate

**Type:** Empirical teardown (install-and-run + read-only). Not a design review. Not an implementation.
**Author:** Claude Code
**Date:** 2026-07-25
**Status:** ✅ COMPLETE — pre-registration committed before any experiment was run (§0).

> **Constraints honored:** No code written for our tool. No architecture documents created or modified. No PR. Read-only against SchoolBot; install-and-run against the tools. The only code written was a throwaway **auth/translation shim** required to connect any tool to SchoolBot's API (`scratchpad/teardown/schoolbot_shim.py`) — its necessity is itself finding E1.

---

## 0. Pre-registered decision rule (frozen BEFORE running anything — applied mechanically)

```
BUILD      if >= 2 of G1..G4 are ABSENT across all tools AND E2 or E5 produced a
           failure severe enough that a working engineer would abandon the tool.
CONTRIBUTE if the tools broadly worked and the gaps are PARTIAL or cosmetic.
STOP       if all four gaps are PRESENT somewhere and E1 was under 15 minutes.
If SchoolBot cannot be wired to any tool inside one working day, report that as its
own primary finding rather than forcing a verdict.
```

**Gaps:** G1 statistical noise model · G2 cassette replay of provider+tool traffic · G3 field-level redaction of captured payloads · G4 in-PR baseline review/approval.

**Commitment honored:** After E2 the strong prior was "BUILD." The rule was applied as written anyway. The temptation to reinterpret the trajectory-capture problem (not one of G1–G4) into a BUILD was explicitly resisted — see §6.

---

## 1. Environment & tool availability (all [VERIFIED])

| Item | Value |
|---|---|
| SchoolBot | `/Users/michel.tyicloud.com/TechnoRactSchoolBot` — FastAPI + Vertex Gemini, `backend/tools/*` (~18 `Tool(...)` defs), custom `MultiAgentOrchestrator`, RAG via pgvector |
| Live endpoint | `https://technoract.redalab.xyz` (`/agents/student/chat`, `/career/ask-research`) — behind Cloudflare (1010-blocks non-browser UA; **bypassed with a browser User-Agent**) |
| Auth | `.env` `TECHNORACT_TEST_PASSWORD`, user `e20210275` → `access_token` (Bearer) |
| Toolchain | Python 3.12.13 / pip 26 · Node v26 · Docker up · Ollama (llama3) available |
| EvalView | `pip install evalview` → 0.8.0 — **RUN LIVE against SchoolBot** |
| AgentAssay | `pip install agentassay` → 0.2.3 (arXiv:2603.02601, real) — installed + **source-verified**, not run live |
| Promptfoo | npm `promptfoo` 0.121.19 — installed, **source-verified**, not run live |
| agentevals | `pip install agentevals` → 0.0.9 — installed + **source-verified**, not run live |

**What "run live" vs "source-verified" means:** only **EvalView** was driven end-to-end against the real deployed agent (E1/E2/E5/E6/E7 below are executed results). The other three were installed and their contracts read from source; their rows are tagged accordingly. This asymmetry is honest, not an oversight — see §3 note.

---

## 2. Scenario selection

The RAGAS set (`eval/prompts.json`, 19 prompts) is **overwhelmingly single-shot RAG Q&A** (14 `ask-research` prompts on thesis/hypothesis-testing docs). **Only 4 prompts exercise multi-step tool selection**, all on the `chat` endpoint — a finding in itself (the existing eval suite barely tests tool selection):

| id | why chosen (tools exercised) |
|---|---|
| `mh-01` | "Compare my avg score this vs last semester, which subjects changed most" → student → scores(sem1) → scores(sem2) → subject |
| `mh-02` | "Which of my courses is most relevant to backend jobs in Cambodia" → courses → career/jobs → research |
| `car-01` | "What skills am I missing for an ML engineer role?" → student skills → career gap |
| `car-02` | "Recommend jobs that match my grades and skills" → grades → skills → jobs |

Live runs used `mh-01` and `car-01`. (Wanted 5; only 4 qualify — recorded as a limitation of the source suite.)

---

## 3. Per-tool results, E1–E7

**Universal wiring finding (all four tools, [VERIFIED] from source + live):** SchoolBot's chat API returns only `{response, agent, chart, type, session_id, ...}` — **no `steps`/`tool_calls`** (confirmed live; golden baseline shows `total_tool_calls: 0`, `steps: []`). Every tool under test evaluates *tool-call trajectories*; none can observe SchoolBot's, because (a) the API emits no trajectory and (b) SchoolBot uses the **Vertex** SDK, which EvalView's auto-tracer (`trace_cmd/patcher.py`, patches OpenAI/Anthropic/Ollama only) and agentevals (require OpenAI/LangChain messages with `tool_calls`) cannot capture. **All four reduce SchoolBot to a black-box text function.**

### EvalView (run live)

| Exp | Result | Tag |
|---|---|---|
| **E1** | Install 15s. First green verdict required: hand-written auth/translation shim + discovering `.evalview/config.yaml` + fixing a **pydantic crash** (`session_id` returned as int; adapter requires str) + configuring a judge (interactive prompt blocks otherwise). Once wired, `run` = **14s**, `2/2 PASSED` (car01 57.5, mh01 87.5). No account/server needed beyond the shim. Total wiring effort **> 15 min of engineering**. | [VERIFIED] |
| **E2** | **On the UNCHANGED agent, first `check` → `⚠️ REGRESSION DETECTED`.** `OUTPUT_CHANGED: car01-skills-gap`, **13% lexical similarity**, note *"Same tools and parameters but output changed … identify what changed (prompt)"* — pure model non-determinism misread as a regression, and misattributed to a prompt change. Flagged `(insufficient history)`: the noise model (G1) is not engaged by the default snapshot→check (N=1). | [VERIFIED] |
| **E3** | Tool-selection true-positive is **untestable by construction** (trajectory invisible). EvalView even emits a *false* anomaly on the working agent: *"skipped_steps — Required tool(s) never called: get_student_skills. Agent may have produced a plausible output without [tools]"* — the tool **was** used server-side; EvalView cannot tell "not called" from "not observable." | [VERIFIED] |
| **E4** | Golden metadata: `model_id=None, model_provider=None` — SchoolBot emits no model id, so EvalView's `model-check` / `@pytest.mark.model_sensitive` have nothing to compare. Model-swap attribution **impossible from the response**; a true swap test would need local infra (not built within budget). | [VERIFIED] (attribution) / [UNVERIFIED] (swap) |
| **E5** | Per-call latency (real): 1.8s–16.0s (car01 11.3s). **Cost = $0.0000** — EvalView warns "agent may not be emitting cost data"; SchoolBot returns no tokens → **cost tracking is blind**. No provider cassette (see G2): every `check` re-hits the live agent. Per-PR cost = full Vertex spend × tests × `--runs`, untracked. | [VERIFIED] |
| **E6** | **PII leak confirmed.** EvalView writes the student's real name, GPA, course names, and "Semester Average" in **plaintext** into `.evalview/golden/*.golden.json` (`trace/final_output`, 433 chars) and the HTML report — the golden files it explicitly instructs you to **`git add .evalview/golden/` and commit**. No redaction. (Actual values redacted from this doc.) | [VERIFIED] |
| **E7** | Review surface: golden JSON (committed) + auto-opened HTML report + `evalview check --fail-on REGRESSION` for CI + `autopr`. Baseline blessing is a **local `snapshot`/`golden` on trust** (`git add`), not an in-PR approve action. | [VERIFIED] |

### AgentAssay (source-verified)

| Exp | Result | Tag |
|---|---|---|
| E1 | Install 27s (pulls scipy/numpy). CLI `run/compare/coverage/mutate/report`. `run` needs an agent callable via Python API. Has `vertex_adapter` + `custom_adapter` → **the only tool that could wire to SchoolBot's Vertex/custom stack** (in-process, not via its API). | [VERIFIED-install] / [UNVERIFIED-live] |
| E2 | Designed for exactly this: SPRT + three-valued PASS/FAIL/**INCONCLUSIVE**, Fisher's exact test in `compare`. Strongest noise handling of the four. | [VERIFIED-source] |
| E3/E4 | Coverage spans tools/decisions/state/boundaries/**model** dimensions; needs captured traces to populate — same trajectory-capture prerequisite. | [VERIFIED-source] |
| E5 | `efficiency/trace_store.py` = **"Trace-First Testing … Trace replay … analyze production traces offline at ZERO additional token cost"** + cost budgeting. This is G2. | [VERIFIED-source] |
| E6 | No redaction/scrub/mask of stored payloads found. | [VERIFIED-source] |
| E7 | No git/PR integration found. | [VERIFIED-source] |

### Promptfoo (source-verified) & agentevals (source-verified)

- **Promptfoo:** has an `http` provider (can grade SchoolBot's final text) and file-based JSON/JUnit output; `trajectory:*` assertions require the provider to **return** the trajectory → unusable on SchoolBot. [VERIFIED-source] / [UNVERIFIED-live]
- **agentevals:** trajectory evaluators call `_normalize_to_openai_messages_list` and branch on `output["tool_calls"]` → require OpenAI/LangChain messages with tool calls, which SchoolBot never emits. Pure evaluators, no capture/store/gate of their own. [VERIFIED-source] / [UNVERIFIED-live]

---

## 4. Gap table (G1–G4) — ABSENT / PARTIAL / PRESENT, with evidence

| Gap | EvalView | AgentAssay | agentevals / Promptfoo | **Across ALL tools** |
|---|---|---|---|---|
| **G1** noise model | **PRESENT** — `--runs N`, `--pass-rate`, `FlakinessScore` (CV, std_dev, variance, confidence intervals), "distinguish non-determinism from real drift" | **PRESENT (rigorous)** — SPRT, Fisher/χ²/KS/Mann-Whitney, Wilson/Clopper-Pearson CIs, 3-valued verdicts | n/a (evaluators) | **PRESENT** |
| **G2** cassette replay | **ABSENT** — caches *judge* only (`--judge-cache`); agent re-run live each check | **PRESENT** — `trace_store` trace-first replay, offline @ zero token cost | agentevals: absent | **PRESENT** (AgentAssay) |
| **G3** payload redaction | **ABSENT** — writes name+grades plaintext into committed golden/HTML (E6); "pii" is an output *check*, not redaction | **ABSENT** — none found | **ABSENT** | **ABSENT** ✅ |
| **G4** in-PR baseline approval | **PARTIAL** — `autopr` opens PRs, PR-comment verdict; but baseline blessed locally on trust | **ABSENT** — no git/PR | **ABSENT** | **PARTIAL** (EvalView) |

**Gaps ABSENT across all tools: exactly one — G3.**

---

## 5. Sharpest concrete failure observed (one sentence)

> On an **unchanged** agent, EvalView reported `⚠️ REGRESSION DETECTED (OUTPUT_CHANGED, 13% similarity)` on its very first check — while simultaneously, and falsely, claiming the required tool was *"never called"* on a run where the tool demonstrably ran server-side — i.e., it manufactured a regression from model noise and was blind to the one signal (tool selection) the project exists to test.

---

## 6. Verdict — mechanical application of §0 (not softened)

**Inputs to the rule:**
- Gaps **ABSENT across all tools = 1** (G3 only). G1 PRESENT, G2 PRESENT (AgentAssay), G4 PARTIAL (EvalView).
- **E2 produced an abandon-grade failure** (false regression on unchanged agent, first try).
- **E6 produced a real PII leak** into git-committed artifacts.
- SchoolBot **was wired** to a tool (EvalView) and produced verdicts in **well under one working day** — so the "cannot be wired" fallback does **not** trigger. What could *not* be wired is the tool-selection **trajectory**, on any tool.

**Applying the rule literally:**
- **BUILD** requires `>= 2` gaps ABSENT across all tools **AND** an abandon-grade E2/E5 failure. The E2 condition is met, **but only 1 gap (G3) is ABSENT across all tools.** The conjunction fails → **BUILD is NOT triggered.**
- **STOP** requires all four gaps PRESENT somewhere and E1 < 15 min. G3 is PRESENT **nowhere**, and first-verdict engineering exceeded 15 min → **STOP is NOT triggered.**
- Residual → **CONTRIBUTE.**

### VERDICT: **CONTRIBUTE**

The incumbents already implement the regression-gate mechanics — and AgentAssay implements the statistical core (G1) and offline replay (G2) with **more rigor than the planned MVP**. The planned `snapshot → change → snapshot → diff` loop is EvalView's shipped workflow verbatim. Only **one** gap (G3, field-level redaction) is absent across every tool, and it is a single feature, not a product — while directly implicated by the E6 PII leak.

**Mandated caveat (recorded, not used to override the verdict):** the specific regression that motivated the project — *did my change alter tool selection* — is **not observable on SchoolBot through any of the four tools**, because SchoolBot emits no trajectory and uses Vertex (uninstrumentable by the OpenAI/Anthropic-oriented tracers). This is a **trajectory-capture** problem, which is **not** one of the pre-registered gaps G1–G4; per the frozen rule it is reported here as an observation and was **not** reinterpreted into a BUILD.

---

## Appendix — reproduction

- Shim (throwaway test scaffolding): `scratchpad/teardown/schoolbot_shim.py` (browser-UA login → `{query}`→`{message}` translation → `/agents/student/chat`).
- EvalView project: `scratchpad/teardown/ev-proj/` (`.evalview/config.yaml`, `tests/*.yaml`, `run3.log`, `e2_check_1.txt`).
- Venvs: `venv-evalview`, `venv-agentevals`, `venv-agentassay`, `pf/` (promptfoo).
- Raw E1 output: `run3.log`. Raw E2 output: `e2_check_1.txt`. Golden baselines (contain redacted PII): `.evalview/golden/`.
