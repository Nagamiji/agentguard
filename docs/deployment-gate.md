# Deployment gate — setup & integration guide

How a team wires AgentGuard into CI so unsafe agent deployments are blocked before merge.
Architecture rationale: `docs/architecture/adr-0013-deployment-gate.md`.

> Consolidates the GitHub Action setup, customer integration, and the gate's security model
> into one page — they overlap enough that three documents would drift out of sync.

## The promise

> Before an AI agent reaches production, AgentGuard evaluates it and blocks unsafe deployments.

Concretely: a CI step runs `agentguard scan`. If the agent would do something the scenarios or
policy forbid, the step **exits non-zero and the merge is blocked**, with the finding shown in
the PR.

## The CLI

Install (until published to a package index, install from the repo):

```bash
pip install agentguard          # once published
# or, from a checkout:  pip install .
```

Commands:

| Command | What it does |
|---|---|
| `agentguard scan --agent A --manifest m.json [--environment prod] [--runner vertex] [--import-library]` | Register the version, evaluate it, gate the deploy. Exits non-zero if blocked. |
| `agentguard evaluate …` | Alias of `scan`. |
| `agentguard report --agent A --fingerprint F` | Verdict for an already-evaluated fingerprint (no run). |
| `agentguard policy check --agent A [--environment prod]` | Fast static pre-check — blocks on a disallowed provider/model/tool with no model run. |
| `agentguard fingerprint m.json` | Compute a manifest's fingerprint locally (no server). |

Common flags: `--api-url` (or `AGENTGUARD_API_URL`), `--api-key` (or `AGENTGUARD_API_KEY`),
`--sarif PATH`, `--json`, `--fail-on {blocked,unknown,any}`.

### Exit codes — the CI contract

```
0   allowed             20  blocked
10  error (fail closed)  30  unknown / never evaluated (fail closed)
```

`--fail-on` default is `unknown`: the step fails on **blocked and unknown**. A gate that exits
0 when it could not tell is not a gate.

## The GitHub Action

`.github/actions/agentguard/action.yml` is a composite action. In a customer repo:

```yaml
name: AI agent gate
on: pull_request

permissions:
  contents: read
  security-events: write   # required to upload SARIF

jobs:
  agentguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Nagamiji/agentguard/.github/actions/agentguard@main
        with:
          api-url: https://agentguard.your-company.com
          api-key: ${{ secrets.AGENTGUARD_API_KEY }}
          agent: customer-support
          manifest: agents/support/manifest.json
          environment: production
          runner: vertex          # real model evaluation (server holds the creds)
          fail-on: unknown        # fail closed
```

The step exits non-zero when the deploy must be blocked (that fails the job), and uploads
SARIF **even on failure** so the developer sees why.

```
Developer → push PR → GitHub Action → AgentGuard API → gate → PASS ✅ / BLOCK ⛔ (job fails)
```

## Security model (the gate)

The gate inherits the platform's guarantees and adds two:

- **Fail closed, end to end.** The server gate is fail-closed (ADR 0008); the CLI is too — any
  error or `unknown` exits non-zero. "We could not tell" never becomes a green check.
- **No real tool execution.** Evaluation simulates the agent; the customer's tools are never
  called (ADR 0008). CI triggering a scan cannot move money or mutate records.
- **Immutable evidence.** Every scan is an append-only `eval_run` with its results and (for
  real runs) the model trace, queryable via the history API.
- **Tenant isolation.** All evaluation and policy data is RLS-scoped; an API key only ever
  sees its own org.
- **Reproducible decisions.** A verdict is keyed to a fingerprint; the same configuration
  yields the same decision, and the run records the policy fingerprint it enforced.
- **Signed verdicts (optional).** With `KEEL_SIGNING_SECRET` set, `GET /gate` returns an HMAC
  `signature` over `(fingerprint, decision, run_id)`. A party that trusts the server and holds
  the key can confirm a verdict carried in a pipeline artifact was not tampered with. This is
  **symmetric integrity, not third-party non-repudiation** — asymmetric signing (Ed25519,
  published public key) is the documented upgrade.

## What is intentionally not here yet

- **Inbound webhooks / push mode** — the pull model (CLI calls API) needs no public callback.
- **A dedicated deployment-audit table** — `eval_runs` already record every evaluation.
- **Async scans** — synchronous today; fine while runs are seconds.

See ADR 0013 for the reasoning behind each.
