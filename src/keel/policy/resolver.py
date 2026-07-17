"""Resolve layered policies into one effective rule set — with provenance.

Precedence (ADR 0012): organization -> project -> agent, lower scope wins. Within a scope,
an environment-specific policy overrides the environment-agnostic one. The caller passes the
applicable policies already ordered from lowest precedence to highest; this reduces them.

Provenance is not a nicety. This resolver lets a lower scope OVERRIDE a higher one, which
means an agent policy can loosen an org limit. That is the precedence the product specifies,
but it is a real risk for a security control, so every effective rule records the scope that
set it — a compiled policy that shows "max_tool_arg: from agent (overrides organization)"
makes the loosening visible in every report instead of silent. (A future 'locked' flag on
org policies is the mitigation; see ADR 0012.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolvedRule:
    value: Any
    source: str  # the scope label that supplied this value, e.g. "organization" / "agent"


def resolve(layers: list[tuple[str, dict[str, Any]]]) -> dict[str, ResolvedRule]:
    """Reduce ordered (label, rules) layers into effective rules with provenance.

    `layers` is lowest-precedence first. A later layer's value for a key wins. An explicit
    None at a later layer CLEARS the rule (a lower scope deliberately removing a limit is a
    decision the audit should show, so it is recorded as a clear, not ignored).
    """
    effective: dict[str, ResolvedRule] = {}
    for label, rules in layers:
        for key, value in rules.items():
            if value is None:
                effective.pop(key, None)
            else:
                effective[key] = ResolvedRule(value=value, source=label)
    return effective


def effective_values(resolved: dict[str, ResolvedRule]) -> dict[str, Any]:
    """Drop provenance — just the rules, for the compiler."""
    return {key: rule.value for key, rule in resolved.items()}
