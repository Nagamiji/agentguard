# CLI Experience v1 — The First 5 Minutes

**Status:** Proposed (final architecture decision, pending Founder approval)
**Author:** Lead Architect (Claude)
**Date:** 2026-07-25
**Related:** `agent-record-format-v1.md`, `architecture-decision-record-v1.md`

---

## Design principle

The core loop must work in **under 5 minutes, offline, with no account**. Every command reads and writes `agent-record.json`. Nothing in this document requires a server.

Command surface (v1, deliberately small):

| Command | Does | Network? |
|---|---|---|
| `agentguard init` | Scaffold `.agentguard/` + `scenarios/` | No |
| `agentguard snapshot` | Record the agent **definition** → `agent-record.json` | No |
| `agentguard run` | Execute one interaction → `run` record (needs a live model) | Model call only |
| `agentguard diff <old> <new>` | Compare two records | No |
| `agentguard test` | Evaluate a record against scenarios → `evaluation` block + gate | Model call only if live |
| `agentguard report <record>` | Emit JSON / HTML / SARIF / JUnit | No |

Exit codes (shared with the gate): `0 ALLOWED` · `30 BLOCKED` · `40 INCOMPLETE`.

---

## The first 5 minutes

### 1. Install
```bash
pip install agentguard
```

### 2. Point it at an agent — `my_agent.py`
```python
import agentguard

@agentguard.record          # L1 manual wrapper — zero magic, works everywhere
def my_agent(user_message: str):
    # your agent, any framework
    ...
    return response
```
(Have no code to decorate yet? `agentguard snapshot --from openai_sdk` or `--from otel trace.json` also works — see `integration-strategy.md`.)

### 3. Snapshot
```bash
$ agentguard snapshot
```
```
✓ Detected agent: refund-agent  (framework: anthropic-sdk)
✓ Prompts: 1 system · Tools: 3 · Model: claude-opus-4-8 (temperature=0)
✓ Fingerprint: sha256:a1b2c3…  (algo: agentguard-fp-1)

  agent-record.json created  (kind: snapshot, execution_mode: static)

Next:  edit your agent, run `agentguard snapshot -o new.json`, then
       `agentguard diff agent-record.json new.json`
```

### 4. Developer changes code
They tweak the system prompt and bump `max_tokens`, then:
```bash
$ agentguard snapshot -o new.json
```

### 5. Diff
```bash
$ agentguard diff agent-record.json new.json
```

---

## `agentguard diff` — the headline output

The output must explain: **what changed · why it matters · confidence · affected tools · behavior differences.** Example (definition-level diff, both `snapshot` records):

```
AgentGuard diff — refund-agent
  old  sha256:a1b2c3…   (2026-07-25 14:03Z)
  new  sha256:9f7e2d…   (2026-07-25 14:19Z)

CHANGED  fingerprint differs → behavior may change.  2 changes, 1 high-impact.

┌─ ● HIGH   Model parameter: max_tokens  256 → 1024
│    Why it matters: longer outputs change tool-argument generation and cost.
│    Affected tools: issue_refund, lookup_order  (arg space widens)
│    Confidence: HIGH — deterministic (definition-level change, exact).
│
└─ ○ LOW    System prompt: reworded (semantically similar)
     old: "You are a refund assistant. Never refund over $100."
     new: "You're a refund helper. Do not refund amounts above $100."
     Why it matters: intent preserved; wording drift can shift refusals.
     Confidence: MEDIUM — text changed; behavioral impact not yet tested.

Unchanged: tools (3), model provider/name, temperature, retrieval.

⚠ This is a DEFINITION diff (execution_mode: static). It shows what CAN change
  behavior, not what DID. To measure actual behavior differences, run:

     agentguard test new.json --runner live
     agentguard diff agent-record.json new.json --behavior
```

Behavior-level diff (`--behavior`, both records are `run`/evaluated):

```
BEHAVIOR diff — refund-agent   (execution_mode: live, N=5)

  Outputs:       2 of 5 scenarios diverged
  Tool calls:    +1 new tool call path  (issue_refund now called on ambiguous input)
  Metrics:       latency 812ms → 1140ms (+40%) · tokens +38% · cost +$0.0016/run

REGRESSIONS  (new failures introduced by `new.json`)
  ● HIGH  authority-spoofing  — old: refused (no tool call)
                                 new: called issue_refund(amount=5000)   ← BLOCKS gate
          Confidence: HIGH — deterministic check over captured decision, stable over N=5.

FIXES  (failures resolved)
  ○      verbose-refusal      — old: failed length check · new: passes

Gate:  new.json → BLOCKED (exit 30).  1 new HIGH regression.
Coverage: 3/10 ASI surfaces tested. Untested: tool runtime, DB perms, tool-response injection.
```

### What each required element maps to
- **what changed** → the CHANGED header + per-item field-level lines.
- **why it matters** → the "Why it matters" line on each item (impact, not just delta).
- **confidence level** → explicit `HIGH / MEDIUM / LOW` with the reason (deterministic vs text-only vs stable-over-N).
- **affected tools** → the "Affected tools" line and the tool-call path changes.
- **behavior differences** → the `--behavior` section (outputs diverged, tool-call paths, metrics, regressions/fixes).

### Honesty rules the diff obeys
- A definition diff never claims behavioral impact it hasn't measured — it says "may change," labels confidence, and points to the live command.
- The gate line uses only `ALLOWED / BLOCKED / INCOMPLETE`, never "secure"/"verified".
- A live behavior verdict is only asserted when it is **stable over N** runs; a flaky result is reported as `INCONCLUSIVE`, not passed or failed.

---

## CI usage (one line)
```bash
agentguard test agent-record.json --runner live --format junit --out results.xml
# exits 0 (ALLOWED) / 30 (BLOCKED) / 40 (INCOMPLETE) — wire straight into any CI gate
```
`INCOMPLETE` (static-only run, behavioral scenarios skipped) is a **non-zero** exit by design — CI never green-lights on unmeasured behavior.
