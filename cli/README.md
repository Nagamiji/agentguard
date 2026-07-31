# AgentGuard CLI

**Security testing for AI agents, before production.** `agentguard` performs an offline
static check or evaluates an agent through an AgentGuard control plane, prints an honest
verdict, and **exits non-zero when a deploy must be blocked or coverage is incomplete**.

The judgement is deterministic (never an LLM deciding what's a vulnerability) and
reproducible: the same configuration always yields the same verdict, explainable to the
engineer it blocks at 2am.

## Install

```bash
pip install agentguard-dev
```

The CLI has two lightweight dependencies (`httpx` and `PyYAML`). Offline static checks need
no API key, network, database, or control plane.

## First local check

```bash
agentguard init
agentguard scan --local
```

Static mode validates the manifest, declared policies, and accidental credentials. It does
not execute a model, so behavioural scenarios are reported as `SKIPPED` and the command
exits `40` (`INCOMPLETE`). To explicitly accept a static-only partial gate in CI:

```bash
agentguard scan --local --allow-incomplete-static --sarif agentguard.sarif
```

## Behaviour simulation through a control plane

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
| `40` | incomplete (behavioural coverage was not run) |

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
