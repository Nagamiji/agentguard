# Baseline golden files persist captured agent output verbatim — no redaction option

EvalView can detect PII in agent output (`ExpectedOutput.no_pii`, `PIIEvaluation`). The same output is then written unredacted to `.evalview/golden/<test>.golden.json` — a path the tool instructs users to `git add` and commit. A tool that recognizes PII persists it to version control by default, with no opt-out for the captured payload.

## Context

Found while evaluating agent regression-testing tools against a production assistant that handles academic records. The assistant returns structured personal data (names, grades, identifiers) in its responses. Running the documented `evalview run` → `evalview snapshot` workflow captures that data verbatim into the golden baseline.

## Reproduction (self-contained, synthetic data only)

### 1. A minimal agent returning personal data

Save as `fake_agent.py`:

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

### 2. EvalView config (`.evalview/config.yaml`)

```yaml
adapter: http
endpoint: http://127.0.0.1:8901/
timeout: 30
allow_private_urls: true
```

### 3. Test case (`tests/grades.yaml`)

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

### 4. Run and snapshot

```bash
evalview run tests --no-judge     # → student-grades ✅ PASSED (87.5)
evalview snapshot --no-judge      # → "BASELINE CAPTURED"
```

### 5. Observe

`.evalview/golden/student-grades.golden.json` now contains the full synthetic record in `trace.final_output`:

```json
{
  "trace": {
    "final_output": "Test Student A, here is your academic summary.\n\n| Course | Score | Grade | GPA |\n|---|---|---|---|\n| FAKE101 Introduction to Testing | 88.0 | A | 3.14 |\n..."
  },
  "output_hash": "3c2cb26f"
}
```

The raw text is present even though a hash is also computed. `snapshot` then prints:

```
2. Commit your goldens so your team shares the baseline:
     git add .evalview/golden/
     git commit -m 'Add agent test baselines'
```

Source: the raw output is written at `core/golden.py:158`; the commit instruction is at `core/celebrations.py:56-58`.

## Impact

Any team following the documented quickstart against an agent that returns personal data in its responses will commit that data, in plaintext, to their repository — and share it via `git` with everyone who has repo access. The risk is proportional to what the agent under test returns; for agents handling user records, financial data, or health information, the golden file becomes a data leak vector that looks like normal test infrastructure.

Users have no signal that this is happening — the `snapshot` output celebrates the capture and encourages committing, but does not warn about payload contents.

## What I am NOT claiming

- This is not a remote exploit and has no attack surface.
- There is no evidence of real-world exposure.
- EvalView's PII detection features (`no_pii`, `PIIEvaluation`) work as designed — they flag PII in agent output, which is genuinely useful. The issue is specifically that detection and persistence are disconnected: recognizing PII does not prevent it from being written to the baseline.
- This is a good-faith bug report. I've used EvalView and think it's a well-built tool.

## Remediation options (cheapest first)

These are suggestions, not demands — you know your codebase best.

**(a) Documentation warning at the commit instruction.** Add a note at `celebrations.py:56-58` warning that golden files contain raw agent output and may include sensitive data. Smallest possible change, closes most of the risk by making it visible.

**(b) Opt-out flag for raw payload persistence.** Something like `--hash-only` or a config option `persist_raw_output: false` that stores only `output_hash` (already computed) without the full `final_output`. Regression detection via hash comparison still works; the raw text stays out of the file.

**(c) Field-level redaction config.** Allow users to specify fields or patterns to redact before persistence — e.g., `redact_patterns: ["Student ID: .*"]` in config.yaml.

**(d) Hashed-value comparison.** For users who want to detect that a specific field *changed* without storing what it contained — hash individual fields and compare hashes across snapshots.

Option (a) alone closes most of the practical risk.

## Offer

Happy to open a PR for whichever direction you prefer. Also happy to hold off on any public discussion until you've had a chance to look.

Tested against: EvalView 0.8.0, Python 3.12, macOS. Reproduction is self-contained and uses only synthetic data.

---

## Private-channel opener

> **Subject: Baseline golden files persist raw agent output — no redaction option**
>
> Hi — I found a data-handling issue in EvalView's snapshot workflow. When an agent returns personal data in its response, `evalview snapshot` writes the full output verbatim into `.evalview/golden/*.golden.json` and instructs the user to `git add` and commit it. There is no redaction, masking, or opt-out for the persisted payload. This is independent of EvalView's PII detection features, which flag PII in output but don't prevent it from being written to the baseline. I have a self-contained reproduction using only synthetic data and a few remediation options ordered by effort. Full writeup attached. Happy to open a PR or hold for your review — let me know your preference.
