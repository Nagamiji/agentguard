# AgentGuard

**An honest pre-deployment gate for AI agents.**

[Website](https://nagamiji.github.io/agentguard/) ·
[Documentation](https://nagamiji.github.io/agentguard/docs/) ·
[PyPI](https://pypi.org/project/agentguard-dev/) ·
[Source](https://github.com/Nagamiji/agentguard)

AgentGuard checks an agent specification before deployment and produces evidence that a
developer or CI pipeline can understand. It reports what was evaluated, what failed, and
what was not tested instead of turning skipped coverage into a green badge.

The CLI is deterministic: an LLM never decides whether something is a vulnerability. The
same specification produces the same fingerprint and explainable result.

## Install

```bash
python -m pip install agentguard-dev
agentguard --version
```

Requires Python 3.12 or newer. The CLI has two lightweight runtime dependencies (`httpx`
and `PyYAML`); it does not install the AgentGuard control plane or a web framework.

## Quick start: offline static check

```bash
agentguard init
# Edit agentguard.yaml with your real prompt, model, tools, and policies.
agentguard scan --local \
  --report-json agentguard-report.json \
  --sarif agentguard-findings.sarif
```

Local mode reads the selected manifest only. It executes no model or real tools, calls no
external API, reads no environment variables, and accesses no production data.

Because behavioural scenarios cannot run without a model, they are reported as `SKIPPED`.
The strict command exits `40` (`INCOMPLETE`) instead of claiming they passed. When your CI
policy intentionally accepts a static-only partial gate, acknowledge that boundary:

```bash
agentguard scan --local --allow-incomplete-static --sarif agentguard-findings.sarif
```

This returns `0` with `ALLOWED (PARTIAL)` while keeping the skipped coverage visible.

## What AgentGuard helps with

- Agent-manifest structure and declared-policy checks
- Accidental credential detection before evidence is written
- Reproducible configuration fingerprints and evidence digests
- Redacted JSON proof objects and SARIF for CI/code-scanning tools
- Fail-closed exit codes for deployment pipelines
- Explicit reporting of skipped scenarios and untested surfaces

## What it does not claim

- AgentGuard does not automatically discover every prompt, tool, and policy from source
  code; describe the real agent in `agentguard.yaml` or `manifest.json`.
- A static check does not prove how a live model will behave.
- Offline mode does not execute tools or validate downstream production side effects.
- It does not replace application tests, red teaming, monitoring, or human security review.

## Configuration

`agentguard init` creates the recommended `agentguard.yaml`, a legacy `manifest.json`, and
a GitHub Actions workflow. Edit the YAML before treating its result as evidence for your
agent—the generated customer-support example is only a template.

AgentGuard auto-discovers files in this order:

1. `agentguard.yaml`
2. `agentguard.yml`
3. `manifest.json`

You can select a file explicitly with `--manifest path/to/agentguard.yaml`.

## Behaviour simulation through a control plane

A configured AgentGuard control plane can evaluate observed model decisions and create an
HTML report:

```bash
export AGENTGUARD_API_KEY=ag_your_key_here

agentguard scan \
  --api-url https://your-agentguard-host \
  --agent my-agent \
  --manifest agentguard.yaml \
  --environment staging \
  --html agentguard-report.html
```

The V1 proof objects are self-attested evidence, not cryptographically signed
attestations. The evidence digest answers “is this the same evidence?”; it is not a
tamper-proof seal.

## Exit codes

| Code | Meaning |
|-----:|:--------|
| `0`  | Allowed, including an explicitly accepted partial static gate |
| `10` | Configuration or execution error |
| `20` | Blocked by a finding at blocking severity |
| `30` | Unknown—the evaluation could not reach a trustworthy decision |
| `40` | Incomplete—behavioural coverage was not run |

## Fingerprint an agent specification

```bash
agentguard fingerprint --manifest agentguard.yaml
```

The fingerprint identifies an exact agent configuration. A result for one fingerprint is
never silently inherited by a changed prompt, model, tool, or policy configuration.

## Project links

- Website: https://nagamiji.github.io/agentguard/
- Documentation: https://nagamiji.github.io/agentguard/docs/
- PyPI: https://pypi.org/project/agentguard-dev/
- GitHub: https://github.com/Nagamiji/agentguard
- Issues: https://github.com/Nagamiji/agentguard/issues

AgentGuard is open source under the Apache-2.0 license. Contributions and real-world agent
integration feedback are welcome.
