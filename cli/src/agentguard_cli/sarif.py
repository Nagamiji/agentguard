"""Render a gate verdict as SARIF 2.1.0 so findings appear in GitHub's Security tab / PR.

SARIF is how a security tool tells GitHub "here are the problems and where they are". Each
AgentGuard finding (a failed check or a static policy violation) becomes one SARIF result;
its severity maps to a SARIF level; the location is the agent manifest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentguard_cli import __version__

if TYPE_CHECKING:
    from agentguard_cli.local import LocalOutcome

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


def build_local_sarif(out: LocalOutcome, *, manifest_uri: str) -> dict[str, Any]:
    """SARIF from Proof Objects.

    The execution mode is baked INTO the ruleId (`agentguard.static.…` vs `…live.…`), not
    only into properties — GitHub's Security tab routinely strips SARIF `properties`, and a
    static "we checked the config" finding must never be mistaken for a live "we tested the
    behaviour" finding. Failed scenarios are results; skipped ones are surfaced as `note`
    so an incomplete run is visible in the tab rather than silently absent.
    """
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for p in out.proofs:
        if p.result == "pass":
            continue
        rule_id = f"agentguard.{p.execution_mode}.{p.asi_id.lower()}.{p.scenario_id}"
        rules.setdefault(
            rule_id,
            {
                "id": rule_id,
                "name": f"[{p.execution_mode.upper()}] {p.name}",
                "shortDescription": {"text": f"{p.asi_id} {p.asi_name}".strip()},
                "properties": {"security-severity": "8.0" if p.result == "fail" else "0.0"},
            },
        )
        if p.result == "fail":
            pc = p.policy_check or {}
            msg = (
                f"[{p.execution_mode.upper()}] {p.name}: expected "
                f"'{p.expected_behavior or pc.get('expected', '')}', observed "
                f"'{pc.get('observed', p.observed_behavior)}'."
            )
            level = "error" if (pc.get("severity") in ("critical", "high")) else "warning"
        else:  # skipped
            msg = f"[{p.execution_mode.upper()}] {p.name}: SKIPPED — {p.skip_reason}"
            level = "note"
        results.append(
            {
                "ruleId": rule_id,
                "level": level,
                "message": {"text": msg},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": manifest_uri}}}],
                "properties": {
                    "execution_mode": p.execution_mode,
                    "result": p.result,
                    "asi": p.asi_id,
                    "expected": p.expected_behavior,
                    "observed": (p.policy_check or {}).get("observed"),
                    "self_attested": p.self_attested,
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
                    "decision": out.decision,
                    "execution_mode": out.execution_mode,
                    "incomplete": out.incomplete,
                    "fingerprint": out.fingerprint,
                    "evidence_digest": out.evidence_digest,
                    "self_attested": True,
                    "cryptographically_verified": False,
                },
            }
        ],
    }
