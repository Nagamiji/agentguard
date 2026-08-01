<p align="center">
  <img src="website/public/logo.svg" alt="AgentGuard logo" width="88" />
</p>

<h1 align="center">AgentGuard</h1>

<p align="center">
  <strong>Know what your AI agent was actually tested for before you deploy it.</strong>
</p>

<p align="center">
  An honest, deterministic reliability and security gate for tool-calling AI agents.
</p>

<p align="center">
  <a href="https://pypi.org/project/agentguard-dev/"><img src="https://img.shields.io/pypi/v/agentguard-dev?label=PyPI&color=2563eb" alt="PyPI version" /></a>
  <a href="https://pypi.org/project/agentguard-dev/"><img src="https://img.shields.io/pypi/pyversions/agentguard-dev" alt="Supported Python versions" /></a>
  <a href="https://github.com/Nagamiji/agentguard/actions/workflows/ci.yml"><img src="https://github.com/Nagamiji/agentguard/actions/workflows/ci.yml/badge.svg" alt="CI status" /></a>
  <a href="https://www.apache.org/licenses/LICENSE-2.0"><img src="https://img.shields.io/badge/license-Apache--2.0-0f766e" alt="Apache-2.0 license" /></a>
</p>

<p align="center">
  <a href="https://nagamiji.github.io/agentguard/">Website</a> ·
  <a href="https://nagamiji.github.io/agentguard/docs/">Documentation</a> ·
  <a href="https://pypi.org/project/agentguard-dev/">PyPI</a> ·
  <a href="https://github.com/Nagamiji/agentguard/issues">Issues</a>
</p>

---

An AI agent can look ready in a demo. Its answers sound safe, the tests are green, and the prompt looks correct.

But deployment needs a better question:

> **What evidence shows that this exact agent configuration is ready to ship?**

AgentGuard checks the prompt, model, tools, and policies declared in an agent specification. It produces a reproducible fingerprint, proof-oriented evidence, machine-readable reports, and a fail-closed exit code for CI.

It also reports what was **not** tested. A skipped behavioural scenario is never presented as a pass.

## Why AgentGuard

| Without a deployment gate | With AgentGuard |
|---|---|
| “The demo looked safe” | The checked configuration has a reproducible fingerprint |
| Skipped tests can disappear inside a green build | Missing behavioural coverage returns `INCOMPLETE` |
| Security policy lives in prompts and tribal knowledge | Prompt, tools, and policies are declared in `agentguard.yaml` |
| CI receives an ambiguous success or failure | CI receives explicit verdicts, exit codes, JSON, and SARIF |
| Evidence may accidentally retain sensitive values | Captured evidence is redacted by default |

## Install

```bash
python -m pip install agentguard-dev
agentguard --version
```

AgentGuard requires Python 3.12 or newer. The standalone CLI has two lightweight runtime dependencies, `httpx` and `PyYAML`; it does not install the FastAPI control plane or worker stack.

## Quick start — no API key required

```bash
agentguard init

# Replace the generated example with your real prompt, model, tools, and policies.
$EDITOR agentguard.yaml

agentguard scan --local \
  --report-json agentguard-report.json \
  --sarif agentguard-findings.sarif
```

Offline mode requires no AgentGuard account, API key, model-provider key, database, or control plane. It does not call a model, execute a real tool, contact an external API, or access production data.

> [!IMPORTANT]
> A strict offline scan normally exits `40` (`INCOMPLETE`). Static checks ran, but behavioural scenarios were skipped because no model was executed. This is an honest coverage boundary, not an installation error.

If your CI policy intentionally accepts a static-only partial gate, acknowledge that explicitly:

```bash
agentguard scan --local \
  --allow-incomplete-static \
  --report-json agentguard-report.json \
  --sarif agentguard-findings.sarif
```

That command returns exit code `0` with `ALLOWED (PARTIAL)` while keeping the skipped coverage visible.

## What it checks today

- Whether the agent specification declares its prompt, model, and tools
- Whether at least one declarative policy is present
- Whether the manifest appears to contain credentials that must not enter evidence
- Whether the configuration produces a stable, reproducible fingerprint
- Which structural checks ran and which behavioural scenarios were skipped
- Whether evidence can be exported as redacted JSON proof objects and SARIF findings

AgentGuard ships five behavioural scenario definitions covering prompt injection, instruction bypass, tool-permission abuse, parameter violations, and data exfiltration. Offline static mode reports those scenarios as `SKIPPED`; they require observed model behaviour to be evaluated.

## How it works

```text
agentguard.yaml
      │
      ▼
manifest + policy + credential checks
      │
      ▼
fingerprint + proof objects + evidence digest
      │
      ▼
verdict + exit code + JSON/SARIF
```

The decision logic is deterministic: an LLM does not decide whether a finding is a vulnerability. The evidence digest helps determine whether two reports contain the same evidence; it is a reproducibility mechanism, not a tamper-proof signature.

## Agent specification

`agentguard init` creates the recommended `agentguard.yaml`, a legacy `manifest.json`, and a starter GitHub Actions workflow.

```yaml
version: "1.0"

agent:
  name: support-agent

model:
  provider: openai
  name: gpt-4o

system_prompt: |
  You are a customer-support agent.
  Never issue a refund above $100 without manager approval.

tools:
  - name: issue_refund
    description: Refund an order to the original payment method.
    schema:
      type: object
      properties:
        order_id:
          type: string
        amount:
          type: number
      required: [order_id, amount]

policies:
  - type: max_tool_arg
    tool: issue_refund
    arg: amount
    max: 100
```

AgentGuard discovers specifications in this order:

1. `agentguard.yaml`
2. `agentguard.yml`
3. `manifest.json`

Select another file with `--manifest path/to/agentguard.yaml`.

## CI/CD

`agentguard init` creates `.github/workflows/agentguard.yml`. A minimal static-only GitHub Actions gate looks like this:

```yaml
name: AgentGuard

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  security-events: write

jobs:
  agentguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install AgentGuard
        run: python -m pip install agentguard-dev

      - name: Run the acknowledged static-only gate
        run: >-
          agentguard scan --local --allow-incomplete-static
          --report-json agentguard-report.json
          --sarif agentguard-findings.sarif

      - name: Upload SARIF
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: agentguard-findings.sarif
```

`--allow-incomplete-static` means your pipeline accepts partial static coverage. It does not convert skipped behavioural scenarios into passes.

## Optional behavioural simulation

The offline workflow above is the default starting point. An API key is required only when you connect the CLI to an AgentGuard control plane for behavioural simulation, reports, or remote policy checks.

```bash
export AGENTGUARD_API_KEY=ag_your_key_here

agentguard scan \
  --api-url https://your-agentguard-host \
  --agent support-agent \
  --manifest agentguard.yaml \
  --environment staging \
  --html agentguard-report.html \
  --sarif agentguard-findings.sarif
```

This is an **AgentGuard control-plane key**, not an OpenAI, Anthropic, Gemini, or other model-provider key. Model-provider credentials, when a live runner needs them, belong on the configured control plane—not in `agentguard.yaml`.

## Modes

| Mode | API key | Network | Model executed | Real tools executed | Result |
|---|---:|---:|---:|---:|---|
| Offline static scan | No | No | No | No | Structural evidence; behavioural scenarios remain skipped |
| Control-plane scan | Yes | Yes | Runner-dependent | No | Observed behavioural evidence and a remote gate verdict |

## Exit-code contract

| Code | Meaning |
|---:|---|
| `0` | Allowed, including an explicitly acknowledged partial static gate |
| `10` | Configuration or execution error |
| `20` | Blocked by a finding at blocking severity |
| `30` | Unknown—the evaluation could not reach a trustworthy decision |
| `40` | Incomplete—required behavioural coverage did not run |

AgentGuard fails closed by default: error, blocked, unknown, and incomplete results are non-zero.

## Useful commands

```bash
# Create agentguard.yaml and a starter CI workflow
agentguard init

# Strict offline static check
agentguard scan --local

# Explicitly accept a partial static-only gate
agentguard scan --local --allow-incomplete-static

# Fingerprint the generated JSON-compatible specification locally
agentguard fingerprint manifest.json

# See every command and option
agentguard --help
agentguard scan --help
```

## What AgentGuard does not claim

- It does not automatically understand an entire source repository. You provide an agent specification describing the real prompt, model, tools, and policies.
- A static scan does not prove how a live model will behave.
- Offline mode does not execute tools or validate downstream production side effects.
- Pattern-based redaction reduces accidental disclosure risk but cannot prove that every sensitive value was detected.
- Proof objects and evidence digests are self-attested evidence, not third-party or cryptographically tamper-proof attestations.
- AgentGuard does not replace application tests, red teaming, production monitoring, or human security review.

The goal is not to put a green badge on every agent. The goal is to make deployment decisions more honest, reproducible, and useful.

## Repository structure

```text
cli/                       Standalone `agentguard` Python package
src/keel/                  FastAPI control plane
src/worker/                Redis-stream worker
tests/                     Unit, integration, security, and isolation tests
website/                   Public website and documentation
edge-worker/               Cloudflare edge gateway
migrations/                Database migrations
infrastructure/terraform/  Infrastructure as code
```

## Development

```bash
git clone https://github.com/Nagamiji/agentguard.git
cd agentguard

cp .env.example .env
make install
make up
make dev

# Run the same lint, type-check, and test gate used by CI
make check
```

The application health endpoint is available at `http://localhost:8000/healthz` during local development.

## Project status

AgentGuard is in public beta. The CLI is published on PyPI as [`agentguard-dev`](https://pypi.org/project/agentguard-dev/). Interfaces and evidence formats may evolve as the project receives real-world integration feedback.

Feedback is especially valuable from teams building tool-calling agents: open an [issue](https://github.com/Nagamiji/agentguard/issues) with the framework, manifest format, CI platform, or automatic-discovery workflow you want AgentGuard to support next.

## License

AgentGuard is available under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
