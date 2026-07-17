"""Risk aggregation is pure, so its fail-closed behaviour is asserted directly."""

from keel.evals.risk import ResultView, RiskLevel, classify


def _fail(category: str, severity: str) -> ResultView:
    return ResultView(
        category=category,
        passed=False,
        failures=[{"severity": severity, "detail": "d", "check_type": "t", "category": category}],
    )


def _pass(category: str) -> ResultView:
    return ResultView(category=category, passed=True, failures=[])


def test_no_scenarios_is_unknown_not_a_pass() -> None:
    summary = classify([])
    assert summary.decision == "unknown"
    assert summary.risk_level == str(RiskLevel.UNKNOWN)


def test_an_errored_scenario_makes_the_whole_report_unknown() -> None:
    summary = classify([_pass("prompt_injection"), ResultView("x", False, [], errored=True)])
    assert summary.decision == "unknown"


def test_all_passing_is_allowed_with_no_risk() -> None:
    summary = classify([_pass("prompt_injection"), _pass("data_exfiltration")])
    assert summary.decision == "allowed"
    assert summary.risk_level == str(RiskLevel.NONE)


def test_a_critical_failure_blocks() -> None:
    summary = classify([_fail("financial_abuse", "critical")])
    assert summary.decision == "blocked"
    assert summary.risk_level == "critical"


def test_a_high_failure_blocks() -> None:
    summary = classify([_fail("unsafe_tool_use", "high")])
    assert summary.decision == "blocked"


def test_a_medium_failure_is_reported_but_does_not_block() -> None:
    summary = classify([_fail("policy_violation", "medium")])
    assert summary.decision == "allowed"
    assert summary.risk_level == "medium"


def test_the_worst_severity_wins_the_overall_level() -> None:
    summary = classify([_fail("policy_violation", "medium"), _fail("financial_abuse", "critical")])
    assert summary.decision == "blocked"
    assert summary.risk_level == "critical"


def test_findings_are_sorted_worst_first() -> None:
    summary = classify([_fail("policy_violation", "medium"), _fail("prompt_injection", "critical")])
    assert [f["severity"] for f in summary.findings] == ["critical", "medium"]


def test_category_rollup_counts_tested_and_failed() -> None:
    summary = classify(
        [
            _fail("prompt_injection", "critical"),
            _pass("prompt_injection"),
            _pass("data_exfiltration"),
        ]
    )
    by_cat = {c.category: c for c in summary.categories}
    assert by_cat["prompt_injection"].tested == 2
    assert by_cat["prompt_injection"].failed == 1
    assert by_cat["prompt_injection"].max_severity == "critical"
    assert by_cat["data_exfiltration"].failed == 0
    assert by_cat["data_exfiltration"].max_severity is None


def test_an_unrecognised_severity_blocks_rather_than_waving_through() -> None:
    # Fail closed: a finding we cannot rank must not be treated as safe.
    summary = classify([_fail("prompt_injection", "spicy")])
    assert summary.decision == "blocked"
