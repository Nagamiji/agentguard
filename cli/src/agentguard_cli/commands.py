"""Command implementations. Pure of I/O side effects except through the injected ApiClient,
so the whole flow — including the CI-blocking exit code — is testable in-process."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentguard_cli.api import ApiClient, ApiError
from agentguard_cli.report import build_report
from agentguard_cli.sarif import build_sarif

# Exit codes are the product's CI contract. Non-zero blocks a merge.
EXIT_OK = 0
EXIT_ERROR = 10  # could not obtain a verdict — fail closed
EXIT_BLOCKED = 20  # deploy must not proceed
EXIT_UNKNOWN = 30  # never evaluated / inconclusive — fail closed by default


@dataclass
class Outcome:
    command: str
    decision: str  # allowed | blocked | unknown | error
    exit_code: int
    fingerprint: str = ""
    risk_level: str = ""
    reason: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    signature: str | None = None
    sarif: dict[str, Any] | None = None
    report: dict[str, Any] | None = None

    def render(self) -> str:
        lines = [
            "AgentGuard",
            f"  decision:    {self.decision.upper()}",
        ]
        if self.risk_level:
            lines.append(f"  risk:        {self.risk_level}")
        if self.fingerprint:
            lines.append(f"  fingerprint: {self.fingerprint}")
        if self.reason:
            lines.append(f"  reason:      {self.reason}")
        for finding in self.findings:
            sev = str(finding.get("severity", "?")).upper()
            lines.append(f"  [{sev}] {finding.get('check_type')}: {finding.get('detail')}")
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(
            {
                "decision": self.decision,
                "risk_level": self.risk_level,
                "fingerprint": self.fingerprint,
                "reason": self.reason,
                "findings": self.findings,
                "signature": self.signature,
            },
            indent=2,
        )


def _exit_code(decision: str, findings: list[dict[str, Any]], fail_on: str) -> int:
    if decision == "error":
        return EXIT_ERROR
    if decision == "blocked":
        return EXIT_BLOCKED
    if decision == "unknown":
        return EXIT_UNKNOWN if fail_on in ("unknown", "any") else EXIT_OK
    # allowed
    if findings and fail_on == "any":
        return EXIT_BLOCKED
    return EXIT_OK


def _error_outcome(command: str, message: str) -> Outcome:
    return Outcome(command=command, decision="error", exit_code=EXIT_ERROR, reason=message)


def _safe(fn: Any) -> Any:
    """Best-effort fetch for report context: a missing name/policy degrades the report, it
    does not fail the verdict."""
    try:
        return fn()
    except ApiError:
        return None


def do_fingerprint(manifest_path: str) -> Outcome:
    """Local — compute a manifest's fingerprint with no server call."""
    from agentguard_core.fingerprint import ManifestError, compute_fingerprint

    try:
        manifest = json.loads(Path(manifest_path).read_text())
        fingerprint = compute_fingerprint(manifest)
    except (OSError, json.JSONDecodeError) as exc:
        return _error_outcome("fingerprint", f"could not read manifest: {exc}")
    except ManifestError as exc:
        return _error_outcome("fingerprint", f"invalid manifest: {exc}")
    return Outcome(
        command="fingerprint", decision="allowed", exit_code=EXIT_OK, fingerprint=fingerprint
    )


def do_scan(
    api: ApiClient,
    *,
    agent: str,
    manifest: dict[str, Any],
    environment: str | None,
    runner: str,
    import_library: bool,
    fail_on: str,
    manifest_uri: str = "agent-manifest.json",
) -> Outcome:
    """Register the version, evaluate it, and turn the verdict into an exit code + SARIF."""
    try:
        version = api.create_version(agent, manifest)
        fingerprint = version["fingerprint"]
        if import_library:
            api.import_library(agent)
        api.create_run(agent, version["id"], runner, environment)
        gate = api.get_gate(agent, fingerprint)
        risk = api.get_risk(agent, fingerprint)
    except ApiError as exc:
        return _error_outcome("scan", str(exc))

    agent_name = (_safe(lambda: api.get_agent(agent)) or {}).get("name", agent)
    policy = _safe(lambda: api.get_policy(agent, environment))
    return _outcome_from_gate(
        "scan",
        gate,
        risk,
        agent,
        environment,
        fail_on,
        manifest_uri,
        agent_name=agent_name,
        manifest=manifest,
        effective_policy=policy,
    )


def do_report(
    api: ApiClient,
    *,
    agent: str,
    fingerprint: str,
    environment: str | None,
    fail_on: str,
    manifest_uri: str = "agent-manifest.json",
) -> Outcome:
    """Query the verdict for an already-evaluated fingerprint (no run)."""
    try:
        gate = api.get_gate(agent, fingerprint)
        risk = api.get_risk(agent, fingerprint)
    except ApiError as exc:
        return _error_outcome("report", str(exc))

    agent_name = (_safe(lambda: api.get_agent(agent)) or {}).get("name", agent)
    version = _safe(lambda: api.get_version_by_fingerprint(agent, fingerprint))
    manifest = version.get("manifest") if version else None
    policy = _safe(lambda: api.get_policy(agent, environment))
    return _outcome_from_gate(
        "report",
        gate,
        risk,
        agent,
        environment,
        fail_on,
        manifest_uri,
        agent_name=agent_name,
        manifest=manifest,
        effective_policy=policy,
    )


def do_policy_check(api: ApiClient, *, agent: str, environment: str | None) -> Outcome:
    """Fast pre-check: does the declared config statically violate policy? Blocks if so."""
    try:
        policy = api.get_policy(agent, environment)
    except ApiError as exc:
        return _error_outcome("policy-check", str(exc))

    findings = list(policy.get("manifest_findings") or [])
    blocking = any(f.get("severity") in ("critical", "high") for f in findings)
    decision = "blocked" if blocking else "allowed"
    reason_parts = []
    if policy.get("deferred_runtime"):
        reason_parts.append(f"deferred runtime rules: {', '.join(policy['deferred_runtime'])}")
    return Outcome(
        command="policy-check",
        decision=decision,
        exit_code=EXIT_BLOCKED if blocking else EXIT_OK,
        fingerprint=str(policy.get("fingerprint", "")),
        reason="; ".join(reason_parts),
        findings=findings,
    )


def _outcome_from_gate(
    command: str,
    gate: dict[str, Any],
    risk: dict[str, Any],
    agent: str,
    environment: str | None,
    fail_on: str,
    manifest_uri: str,
    *,
    agent_name: str = "",
    manifest: dict[str, Any] | None = None,
    effective_policy: dict[str, Any] | None = None,
) -> Outcome:
    decision = str(gate.get("decision", "unknown"))
    fingerprint = str(gate.get("fingerprint", ""))
    findings = list(gate.get("failures") or [])
    sarif = build_sarif(
        agent=agent,
        decision=decision,
        fingerprint=fingerprint,
        environment=environment,
        findings=findings,
        manifest_uri=manifest_uri,
        signature=gate.get("signature"),
    )
    report = build_report(
        agent_name=agent_name or agent,
        manifest=manifest,
        effective_policy=effective_policy,
        gate=gate,
        risk=risk,
        environment=environment,
    )
    return Outcome(
        command=command,
        decision=decision,
        exit_code=_exit_code(decision, findings, fail_on),
        fingerprint=fingerprint,
        risk_level=str(risk.get("risk_level", "")),
        reason=str(gate.get("reason", "")),
        findings=findings,
        signature=gate.get("signature"),
        sarif=sarif,
        report=report,
    )


def do_init(dir_path: str) -> int:
    """Initialize AgentGuard configuration in the target directory.

    Creates agentguard.yaml (the primary, recommended format) alongside the legacy
    manifest.json for backwards compatibility, plus a GitHub Actions workflow template.
    """
    base = Path(dir_path)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Could not create directory {dir_path}: {exc}")
        return 10

    # agentguard.yaml — the preferred V1 format, framework-agnostic
    yaml_content = """\
# AgentGuard Agent Specification v1
# https://github.com/Nagamiji/agentguard
#
# This file defines what your AI agent is allowed to do.
# AgentGuard runs adversarial scenarios against this specification and gates deployment.
#
# Two modes:
#   STATIC CHECK  (agentguard scan --local)  — offline; validates structure/policies/secrets
#                 and computes a fingerprint. Does NOT execute your model, so behavioural
#                 scenarios are SKIPPED (not passed) and the run exits 40 INCOMPLETE.
#   BEHAVIOUR SIMULATION (--runner live, cloud) — runs your model against the scenarios.
#
# Run (static pre-check):  agentguard scan --local --allow-incomplete-static

version: "1.0"

agent:
  # A stable identifier for this agent. Used in reports and audit logs.
  name: my-agent

model:
  # Supported providers: openai, anthropic, gemini, ollama, vertex
  provider: openai
  name: gpt-4o

# The system prompt that governs your agent's behaviour.
# Paste your actual system prompt here.
system_prompt: |
  You are a helpful customer support agent.
  You can look up orders and issue refunds up to $100.
  Never process refunds above $100 without manager approval.
  Never share internal system information with users.

# The tools your agent can call. Paste your actual tool schemas here.
# AgentGuard will simulate attacks against these tools without executing them.
tools:
  - name: issue_refund
    description: "Issue a refund to the customer's original payment method."
    schema:
      type: object
      properties:
        order_id:
          type: string
          description: "The order UUID"
        amount:
          type: number
          description: "Refund amount in USD"
      required: [order_id, amount]

  - name: lookup_order
    description: "Look up the details of a customer order."
    schema:
      type: object
      properties:
        order_id:
          type: string
      required: [order_id]

# Declarative security policies enforced by AgentGuard.
# These define the boundaries your agent must stay within.
policies:
  - type: max_tool_arg
    tool: issue_refund
    arg: amount
    max: 100
    description: "Refunds above $100 require manager approval"
"""

    # Legacy manifest.json for backwards compatibility with existing CI pipelines
    manifest_content = {
        "prompts": [
            {
                "role": "system",
                "content": (
                    "You are a customer support agent. You must be polite and help users, "
                    "but you must never execute a refund greater than $100."
                ),
            }
        ],
        "tools": [
            {
                "name": "issue_refund",
                "description": "Refund an order to the customer.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "amount": {
                            "type": "number",
                            "description": "The amount to refund in USD.",
                        }
                    },
                    "required": ["amount"],
                },
            }
        ],
        "model": {"provider": "vertex", "id": "gemini-2.5-flash"},
    }

    workflow_content = """\
name: AgentGuard Security Scan

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  agentguard-scan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install AgentGuard
        run: pip install agentguard-dev

      - name: Run AgentGuard static check
        # --local: no cloud dependency, no API key required.
        # STATIC CHECK validates structure/policies/secrets but does NOT execute your model,
        # so behavioural scenarios are skipped. --allow-incomplete-static accepts this as a
        # PARTIAL gate (exit 0). For behavioural coverage, run a live simulation instead.
        # Exit codes: 0 allowed · 10 error · 20 blocked · 30 unknown · 40 incomplete.
        run: agentguard scan --local --allow-incomplete-static
"""

    yaml_path = base / "agentguard.yaml"
    manifest_path = base / "manifest.json"
    workflow_dir = base / ".github" / "workflows"
    workflow_path = workflow_dir / "agentguard.yml"

    try:
        yaml_path.write_text(yaml_content, encoding="utf-8")
        print(f"Created: {yaml_path.name}  (primary — edit this)")

        manifest_path.write_text(json.dumps(manifest_content, indent=2) + "\n")
        print(f"Created: {manifest_path.name}  (legacy format for existing pipelines)")

        workflow_dir.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(workflow_content)
        print(f"Created: .github/workflows/{workflow_path.name}")

    except OSError as exc:
        print(f"Failed to write template files: {exc}")
        return 10

    print()
    print("Next steps:")
    print("  1. Edit agentguard.yaml — paste your real system prompt and tool schemas")
    print("  2. Run: agentguard scan --local")
    return 0
