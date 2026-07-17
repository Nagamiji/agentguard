"""Render a gate verdict as SARIF 2.1.0 so findings appear in GitHub's Security tab / PR.

SARIF is how a security tool tells GitHub "here are the problems and where they are". Each
AgentGuard finding (a failed check or a static policy violation) becomes one SARIF result;
its severity maps to a SARIF level; the location is the agent manifest.
"""

from __future__ import annotations

from typing import Any

from agentguard_cli import __version__

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_INFO_URI = "https://github.com/Nagamiji/agentguard"


def _level(severity: str) -> str:
    # SARIF levels: error | warning | note. Blocking severities are errors.
    return {"critical": "error", "high": "error", "medium": "warning", "low": "note"}.get(
        severity, "warning"
    )


def build_sarif(
    *,
    agent: str,
    decision: str,
    fingerprint: str,
    environment: str | None,
    findings: list[dict[str, Any]],
    manifest_uri: str,
    signature: str | None = None,
) -> dict[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for finding in findings:
        rule_id = str(finding.get("check_type", "agentguard.finding"))
        rules.setdefault(
            rule_id,
            {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": rule_id.replace("_", " ")},
            },
        )
        results.append(
            {
                "ruleId": rule_id,
                "level": _level(str(finding.get("severity", ""))),
                "message": {"text": str(finding.get("detail", "AgentGuard finding"))},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": manifest_uri},
                        }
                    }
                ],
                "properties": {
                    "category": finding.get("category"),
                    "severity": finding.get("severity"),
                    "agent": agent,
                    "fingerprint": fingerprint,
                    "decision": decision,
                    "environment": environment,
                },
            }
        )

    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "AgentGuard",
                        "informationUri": _INFO_URI,
                        "version": __version__,
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
                "properties": {
                    "decision": decision,
                    "fingerprint": fingerprint,
                    "environment": environment,
                    "signature": signature,
                },
            }
        ],
    }
