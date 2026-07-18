# AgentGuard CLI

**Security testing for AI agents, before production.** `agentguard` evaluates an agent
version against its scenarios and policy, prints a verdict, and **exits non-zero when a
deploy must be blocked** — so a CI step fails and stops the merge. That exit code is the
whole point.

The judgement is deterministic (never an LLM deciding what's a vulnerability) and
reproducible: the same configuration always yields the same verdict, explainable to the
engineer it blocks at 2am.

## Install

```bash
pip install agentguard-dev
```

The CLI is a thin API client — its only dependency is `httpx`. It talks to an AgentGuard
control plane (self-hosted or hosted).

## First scan

```bash
export AGENTGUARD_API_KEY=ag_your_key_here     # from your org's onboarding

agentguard scan \
  --api-url https://your-agentguard-host \
  --agent my-support-bot \
  --manifest manifest.json \
  --environment prod \
  --html report.html
```

Exit codes are the CI contract:

| Code | Meaning |
|-----:|:--------|
| `0`  | allowed |
| `20` | blocked (a scenario failed at blocking severity) |
| `10` | error |
| `30` | unknown (could not evaluate — fail closed) |

`--html report.html` writes a self-contained report (no external requests) with the
verdict, evidence, and a per-finding remediation.

## Compute a fingerprint locally

```bash
agentguard fingerprint --manifest manifest.json
```

The fingerprint identifies an exact agent configuration; a verdict is bound to it, so v2
never inherits v1's pass.

## More

`agentguard --help` lists every command. Full docs and the control-plane setup live in the
[repository](https://github.com/Nagamiji/agentguard).
