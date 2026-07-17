"""Compile effective policy rules into what the evaluation engine actually enforces.

Two outputs, because a policy is enforced in two moments:

  * `derived_checks` — check specs (the same shape scenarios use) merged into every scenario
    run. This is how "refund <= $100" is enforced: not by hardcoding 100 anywhere, but by the
    policy generating a `tool_arg_limit` check that the existing engine applies.
  * `manifest_findings` — STATIC violations decided at compile time against the agent's
    declared manifest, needing no model run. A disallowed provider or a declared forbidden
    tool is wrong regardless of what the agent does at runtime, so it blocks immediately.

`deferred_runtime` lists rules that were declared but cannot be enforced at deploy time
(ADR 0012), so a report can say so out loud rather than implying full coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from keel.policy.rules import RUNTIME_DECLARED


@dataclass
class CompiledPolicy:
    derived_checks: list[dict[str, Any]] = field(default_factory=list)
    manifest_findings: list[dict[str, Any]] = field(default_factory=list)
    deferred_runtime: list[str] = field(default_factory=list)


def _finding(check_type: str, category: str, severity: str, detail: str) -> dict[str, str]:
    return {"check_type": check_type, "category": category, "severity": severity, "detail": detail}


def _manifest_tool_names(manifest: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for tool in manifest.get("tools") or []:
        if isinstance(tool, dict) and isinstance(tool.get("name"), str):
            names.append(tool["name"])
    return names


def compile_policy(rules: dict[str, Any], manifest: dict[str, Any]) -> CompiledPolicy:
    compiled = CompiledPolicy()
    tool_names = _manifest_tool_names(manifest)
    model = manifest.get("model") if isinstance(manifest.get("model"), dict) else {}
    provider = str(model.get("provider", "")) if model else ""
    model_id = str(model.get("id", "")) if model else ""

    # --- rules that become checks applied during a scan ---

    for entry in rules.get("max_tool_arg") or []:
        compiled.derived_checks.append(
            {
                "type": "tool_arg_limit",
                "tool": entry["tool"],
                "arg": entry["arg"],
                "max": entry["max"],
                "category": "unsafe_tool_use",
                "severity": "critical",
            }
        )

    for tool in rules.get("forbidden_tools") or []:
        compiled.derived_checks.append(
            {
                "type": "must_not_call_tool",
                "tool": tool,
                "category": "unsafe_tool_use",
                "severity": "critical",
            }
        )

    allowed_tools = rules.get("allowed_tools")
    if allowed_tools is not None:
        # Anything the agent declares that is not allow-listed must never be called.
        for tool in tool_names:
            if tool not in allowed_tools:
                compiled.derived_checks.append(
                    {
                        "type": "must_not_call_tool",
                        "tool": tool,
                        "category": "unsafe_tool_use",
                        "severity": "high",
                    }
                )

    max_calls = rules.get("max_tool_calls")
    if isinstance(max_calls, int) and not isinstance(max_calls, bool):
        compiled.derived_checks.append(
            {
                "type": "max_tool_calls",
                "max": max_calls,
                "category": "unsafe_tool_use",
                "severity": "high",
            }
        )

    # --- static violations of the declared config (no run needed) ---

    allowed_providers = rules.get("allowed_providers")
    if allowed_providers is not None and provider and provider not in allowed_providers:
        compiled.manifest_findings.append(
            _finding(
                "policy_allowed_providers",
                "policy_violation",
                "critical",
                f"agent uses model provider '{provider}', not in the allowed set "
                f"{sorted(allowed_providers)}",
            )
        )

    allowed_families = rules.get("allowed_model_families")
    if allowed_families is not None and model_id:
        if not any(model_id.lower().startswith(fam.lower()) for fam in allowed_families):
            compiled.manifest_findings.append(
                _finding(
                    "policy_allowed_model_families",
                    "policy_violation",
                    "critical",
                    f"agent uses model '{model_id}', not in an allowed family "
                    f"{sorted(allowed_families)}",
                )
            )

    for tool in rules.get("forbidden_tools") or []:
        if tool in tool_names:
            compiled.manifest_findings.append(
                _finding(
                    "policy_forbidden_tool_declared",
                    "policy_violation",
                    "critical",
                    f"agent declares forbidden tool '{tool}'",
                )
            )

    if allowed_tools is not None:
        for tool in tool_names:
            if tool not in allowed_tools:
                compiled.manifest_findings.append(
                    _finding(
                        "policy_tool_not_allowed",
                        "policy_violation",
                        "high",
                        f"agent declares tool '{tool}', not in allowed {sorted(allowed_tools)}",
                    )
                )

    # --- honestly-deferred runtime rules ---
    compiled.deferred_runtime = sorted(k for k in rules if k in RUNTIME_DECLARED)

    return compiled
