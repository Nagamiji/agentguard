# Reproducer — captured agent output is persisted verbatim into the committed baseline (no redaction)

**Component:** EvalView CLI
**Version:** 0.8.0 (`pip show evalview`)
**Environment:** Python 3.12.13, macOS; EvalView installed from PyPI. HTTP adapter.
**Class:** Sensitive-data handling — captured model output written unredacted to a file the tool instructs users to commit to version control.
**Data in this report:** 100% synthetic. No real person or record appears.

---

## Summary

When EvalView snapshots a baseline, it stores the agent's **full final output verbatim** in `.evalview/golden/<test>.golden.json` (field `trace.final_output`). If the agent's response contains user records — names, IDs, grades, free-text — those land in the golden file **in plaintext**. The tool then instructs the user to `git add .evalview/golden/` and commit it. There is **no redaction, masking, hashing, or field-exclusion option** for the captured payload. [VERIFIED]

This is independent of EvalView's PII feature set: EvalView offers PII *detection* (an opt-in evaluator that flags whether the agent's output contains PII), but detection does not prevent that same output from being persisted verbatim into the baseline and report. [VERIFIED]

---

## Reproduction (self-contained, synthetic)

### Step 0 — a minimal agent that returns final text only

Many production agents return only a final answer over HTTP (no step/tool-call trace). Save as `fake_agent.py`:

```python
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

SYNTHETIC_RESPONSE = (
    "Test Student A, here is your academic summary.\n\n"
    "| Course | Score | Grade | GPA |\n"
    "|---|---|---|---|\n"
    "| FAKE101 Introduction to Testing | 88.0 | A | 3.14 |\n"
    "| FAKE202 Synthetic Methods | 79.0 | B+ | 3.14 |\n"
    "| Semester Average | 83.5 | A- | 3.14 |\n\n"
    "Student ID: TEST-0001. Advising note: focus on FAKE202 next term."
)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); self.rfile.read(n)
        out = json.dumps({
            "response": SYNTHETIC_RESPONSE,
            "session_id": "synthetic-session-1",
            "agent": "academic", "type": "academic", "status": "success",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8901), Handler).serve_forever()
```

```bash
python3 fake_agent.py &
```

### Step 1 — point EvalView at it (`.evalview/config.yaml`)

```yaml
adapter: http
endpoint: http://127.0.0.1:8901/
timeout: 30
allow_private_urls: true
```

### Step 2 — one test case (`tests/grades.yaml`)

```yaml
name: "student-grades"
description: "Agent returns a student record as final text"
input:
  query: "What are my grades this semester?"
expected:
  output:
    not_contains: ["I don't have access"]
thresholds:
  min_score: 50
```

### Step 3 — run and snapshot (the documented quickstart flow)

```bash
evalview run tests --no-judge          # → student-grades ✅ PASSED (87.5)
evalview snapshot --no-judge           # → "BASELINE CAPTURED"
```

`snapshot` prints (source: `evalview/core/celebrations.py:56-58`):

```
2. Commit your goldens so your team shares the baseline:
     git add .evalview/golden/
     git commit -m 'Add agent test baselines'
```

---

## Expected vs Actual

- **Expected:** the persisted baseline stores enough to detect regressions (e.g., an output hash and/or structured checks) without embedding raw user-record content, **or** provides a documented option to redact/exclude/hash captured payload fields before they are written to a file destined for commit.
- **Actual:** `.evalview/golden/student-grades.golden.json` stores `trace.final_output` verbatim — the entire synthetic record (name, GPA, per-course grades, student ID, advising note) — alongside an `output_hash`. The raw text is present even though a hash is also computed (`evalview/core/golden.py:158`). No redaction path exists.

---

## The written artifact (synthetic golden, inline)

```json
{
  "metadata": { "test_name": "student-grades", "score": 87.5, "version": 1,
    "model_id": null, "model_provider": null },
  "trace": {
    "session_id": "synthetic-session-1",
    "steps": [],
    "final_output": "Test Student A, here is your academic summary.\n\n| Course | Score | Grade | GPA |\n|---|---|---|---|\n| FAKE101 Introduction to Testing | 88.0 | A | 3.14 |\n| FAKE202 Synthetic Methods | 79.0 | B+ | 3.14 |\n| Semester Average | 83.5 | A- | 3.14 |\n\nStudent ID: TEST-0001. Advising note: focus on FAKE202 next term.",
    "metrics": { "total_cost": 0.0, "total_latency": 35.6, "total_tokens": null },
    "trace_context": { "total_llm_calls": 0, "total_tool_calls": 0 }
  },
  "tool_sequence": [],
  "output_hash": "3c2cb26f"
}
```

(`steps: []` / `total_tool_calls: 0` reflect that a final-text-only agent exposes no trajectory — orthogonal to this report, noted only to show the response shape.)

---

## No redaction option — verification detail

Searched source and packaged docs of evalview 0.8.0 for `redact`, `mask`, `scrub`, `sanitize`, `anonymize`, `exclude_field`, `drop_field`, `hash_output`, `pii_filter`:
- `core/security.py::sanitize_for_llm` — sanitizes text before it is placed **into an LLM prompt** (control-char stripping, truncation for prompt-injection mitigation). Not payload redaction. [VERIFIED]
- `core/types.py` — `ExpectedOutput.no_pii`, `pii` check flag, `PIIEvaluation(has_pii, passed)` — these **detect** PII in the agent's output and can fail a test; they do **not** redact what is persisted. [VERIFIED]
- No masking/hashing/exclusion is applied to `trace.final_output` before it is written to the golden or HTML report. [VERIFIED]

**Impact:** any team following the documented quickstart against an agent that returns user data in its response will commit that data, in plaintext, to their repository — and share it via `git` with everyone who has repo access.
