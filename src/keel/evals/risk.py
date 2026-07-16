"""Risk aggregation: turn one run's per-scenario results into a report a human can act on.

Pure functions over plain dicts — no database, no I/O — so the classification that a customer's
security team will scrutinise is trivially testable and cannot depend on request state.

Fail-closed, consistent with the gate (ADR 0008): an errored run is UNKNOWN, never a clean
bill of health, and an unrecognised severity never silently outranks a real critical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from keel.evals.engine import BLOCKING_SEVERITIES
from keel.evals.taxonomy import max_severity, severity_rank


class RiskLevel(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"  # everything tested, nothing failed
    UNKNOWN = "unknown"  # not evaluated, or the run could not complete


@dataclass(frozen=True)
class ResultView:
    """One scenario's outcome, reduced to what risk cares about."""

    category: str
    passed: bool
    failures: list[dict[str, Any]]  # each carries at least 'severity' and 'detail'
    errored: bool = False


@dataclass(frozen=True)
class CategoryRisk:
    category: str
    tested: int
    failed: int
    max_severity: str | None


@dataclass
class RiskSummary:
    decision: str  # allowed | blocked | unknown  (same vocabulary as the gate)
    risk_level: str
    reason: str
    categories: list[CategoryRisk] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)


def _blocking(severity: str) -> bool:
    try:
        from keel.evals.checks import Severity

        return Severity(severity) in BLOCKING_SEVERITIES
    except ValueError:
        # An unknown severity is treated as blocking: better to over-block on a malformed
        # finding than to wave a deploy through because we could not parse its severity.
        return True


def classify(views: list[ResultView]) -> RiskSummary:
    if not views:
        return RiskSummary(
            decision="unknown",
            risk_level=str(RiskLevel.UNKNOWN),
            reason="No scenarios were evaluated for this configuration.",
        )

    if any(v.errored for v in views):
        return RiskSummary(
            decision="unknown",
            risk_level=str(RiskLevel.UNKNOWN),
            reason="At least one scenario could not complete, so overall safety is unknown.",
        )

    # Per-category rollup.
    by_category: dict[str, list[ResultView]] = {}
    for view in views:
        by_category.setdefault(view.category, []).append(view)

    categories: list[CategoryRisk] = []
    for category, group in sorted(by_category.items()):
        failed = [v for v in group if not v.passed]
        sevs = [f["severity"] for v in failed for f in v.failures if "severity" in f]
        worst = max_severity(sevs)
        categories.append(
            CategoryRisk(
                category=category,
                tested=len(group),
                failed=len(failed),
                max_severity=str(worst) if worst else None,
            )
        )

    # Flat, severity-sorted list of every finding, for the top of the report.
    findings = [
        {**failure, "category": view.category}
        for view in views
        if not view.passed
        for failure in view.failures
    ]
    findings.sort(key=lambda f: severity_rank(str(f.get("severity", ""))), reverse=True)

    if not findings:
        total = len(views)
        return RiskSummary(
            decision="allowed",
            risk_level=str(RiskLevel.NONE),
            reason=f"All {total} scenarios passed.",
            categories=categories,
        )

    all_sevs = [str(f.get("severity", "")) for f in findings]
    worst_overall = max_severity(all_sevs)
    blocked = any(_blocking(s) for s in all_sevs)
    risk_level = str(worst_overall) if worst_overall else str(RiskLevel.LOW)

    failed_count = sum(1 for v in views if not v.passed)
    if blocked:
        reason = (
            f"{failed_count} of {len(views)} scenarios failed, including blocking-severity "
            "findings. This configuration must not deploy."
        )
    else:
        reason = (
            f"{failed_count} of {len(views)} scenarios failed at advisory severity. Review, "
            "but the deploy is not blocked."
        )

    return RiskSummary(
        decision="blocked" if blocked else "allowed",
        risk_level=risk_level,
        reason=reason,
        categories=categories,
        findings=findings,
    )
