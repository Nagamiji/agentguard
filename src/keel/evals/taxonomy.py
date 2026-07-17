"""The attack/failure taxonomy and severity model.

This is the vocabulary the whole product reports in. It is deliberately its own module: the
taxonomy — the categories of ways an agent can be dangerous, and how severe each is — is part
of what AgentGuard sells, not an implementation detail of one endpoint.

`ScenarioCategory` is the bucket a *scenario* belongs to (what kind of risk it probes). It is
a different axis from `checks.FailureCategory`, which is the reason a single *check* failed.
One prompt-injection scenario can fail a `data_leakage` check; both facts are true and useful.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from keel.evals.checks import Severity


class ScenarioCategory(StrEnum):
    """The eight risk categories AgentGuard's library probes.

    Ordered roughly by how directly they map to money and access — the ICP is agents that
    touch refunds, payments and accounts.
    """

    PROMPT_INJECTION = "prompt_injection"
    DATA_EXFILTRATION = "data_exfiltration"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    UNSAFE_TOOL_USE = "unsafe_tool_use"
    FINANCIAL_ABUSE = "financial_abuse"
    HALLUCINATED_ACTION = "hallucinated_action"
    POLICY_VIOLATION = "policy_violation"
    SENSITIVE_DATA_EXPOSURE = "sensitive_data_exposure"


# Higher = worse. Used to roll many findings up to one number without an opinion getting in.
SEVERITY_ORDER: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


def severity_rank(value: str) -> int:
    """Rank a severity string, tolerating an unknown value as the lowest (fail-safe-loud:
    an unrecognised severity should never out-rank a real critical)."""
    try:
        return SEVERITY_ORDER[Severity(value)]
    except ValueError:
        return -1


def max_severity(values: Iterable[str]) -> Severity | None:
    """The worst severity in a set, or None if the set is empty."""
    ranked = sorted((severity_rank(v), v) for v in values)
    if not ranked or ranked[-1][0] < 0:
        return None
    return Severity(ranked[-1][1])
