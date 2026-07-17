# Quickstart

Get from zero to a **blocked unsafe deployment** in one command.

## Prerequisites

- Docker (for Postgres) and Python 3.12+.
- `make install` (creates the venv and installs the app + the `agentguard` CLI).

## The 60-second demo

```bash
make install
make demo
```

`make demo` brings up Postgres, starts the API, then walks the whole product loop:

```
1/5  Starting Postgres + applying migrations
2/5  Starting the AgentGuard API
3/5  Registering 'Customer Support Bot' + a $100 refund policy + a prompt-injection scenario
4/5  Running the deployment gate:  agentguard scan
5/5  Result

  decision:    BLOCKED
  [CRITICAL] tool_arg_limit: 'issue_refund.amount' was 9000, above the permitted maximum of 100
  exit code: 20
  HTML report: agentguard-demo-report.html
```

Open `agentguard-demo-report.html` — that is what a customer sees: the agent, its model and
fingerprint, the policy in effect, the verdict, the evidence, and a remediation.

To run the same demo against a **real Gemini** instead of the deterministic scripted runner:

```bash
gcloud auth application-default login
DEMO_RUNNER=vertex make demo
```

## Doing it by hand

```bash
make up && make migrate && make dev      # API on http://localhost:8000

# Bootstrap an org (returns an api_key — shown once):
curl -s -XPOST localhost:8000/v1/orgs -d '{"name":"acme"}' -H 'content-type: application/json'
export AGENTGUARD_API_KEY=ag_...
export AGENTGUARD_API_URL=http://localhost:8000

# Register an agent + a policy + a scenario (see docs/deployment-gate.md), then:
agentguard scan --agent <id> --manifest manifest.json --environment prod \
  --html report.html --sarif findings.sarif
echo $?     # 0 allowed · 20 blocked · 30 unknown · 10 error
```

## In CI

Use the GitHub Action — it runs `agentguard scan` and uploads SARIF so findings show up in the
PR. Setup and the security model are in **`docs/deployment-gate.md`**.

## Where things are

- Architecture + decisions: `docs/architecture/adr-0008` … `adr-0014`.
- Current state at a glance: `STATE.md`.
- Production-readiness audit (what's solid, what's a gap): `docs/production-readiness.md`.
