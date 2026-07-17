"""Customer-facing report: structure, remediation, and safe HTML rendering. No DB."""

import json

from agentguard_cli.report import build_report, recommend, render_html, render_json

GATE = {
    "decision": "blocked",
    "fingerprint": "a99a450d603e1c25511c0cf8f06a122a54c691e999cc475cdd9b0df3db49dd7e",
    "reason": "1 of 1 scenarios failed with blocking severity.",
    "signature": "deadbeef" * 8,
    "failures": [
        {
            "check_type": "tool_arg_limit",
            "severity": "critical",
            "category": "unsafe_tool_use",
            "detail": "'issue_refund.amount' was 9000, above the permitted maximum of 100",
        }
    ],
}
RISK = {"risk_level": "critical"}
MANIFEST = {"model": {"provider": "vertex", "id": "gemini-2.5-flash"}}
POLICY = {
    "effective": {
        "max_tool_arg": {
            "value": [{"tool": "issue_refund", "arg": "amount", "max": 100}],
            "source": "organization",
        }
    },
    "deferred_runtime": ["human_approval_required"],
}


def _report() -> dict:
    return build_report(
        agent_name="Customer Support Bot",
        manifest=MANIFEST,
        effective_policy=POLICY,
        gate=GATE,
        risk=RISK,
        environment="prod",
    )


# --- remediation ------------------------------------------------------------------------


def test_every_shipped_check_type_has_a_recommendation() -> None:
    for check_type in (
        "tool_arg_limit",
        "must_not_call_tool",
        "must_not_use_tools",
        "must_not_output",
        "max_tool_calls",
        "policy_allowed_providers",
        "policy_forbidden_tool_declared",
    ):
        assert recommend(check_type) and "Review the finding" not in recommend(check_type)


def test_an_unknown_check_type_gets_a_generic_recommendation() -> None:
    assert "Review the finding" in recommend("some_future_check")


# --- structure --------------------------------------------------------------------------


def test_report_carries_the_verdict_model_policy_and_remediation() -> None:
    report = _report()
    assert report["agent"] == "Customer Support Bot"
    assert report["model"] == "gemini-2.5-flash"
    assert report["decision"] == "blocked"
    assert report["risk_level"] == "critical"
    assert report["policy"][0]["rule"] == "max_tool_arg"
    assert report["policy"][0]["source"] == "organization"
    assert report["deferred_runtime_rules"] == ["human_approval_required"]
    finding = report["findings"][0]
    assert finding["check_type"] == "tool_arg_limit"
    assert "9000" in finding["detail"]
    assert finding["recommendation"]  # actionable, not empty
    assert "generated_at" in report


def test_report_json_round_trips() -> None:
    parsed = json.loads(render_json(_report()))
    assert parsed["findings"][0]["recommendation"]


# --- HTML rendering ---------------------------------------------------------------------


def test_html_shows_the_verdict_evidence_and_recommendation() -> None:
    html = render_html(_report())
    assert "Customer Support Bot" in html
    assert "BLOCKED" in html
    assert "gemini-2.5-flash" in html
    assert "9000" in html  # the evidence
    assert "Recommendation" in html and "Tighten the policy" in html


def test_html_is_self_contained() -> None:
    html = render_html(_report())
    # No external requests: a report must open offline and leak nothing when viewed.
    for external in ("http://", "https://cdn", "<script", "src=", "<link"):
        assert external not in html


def test_html_escapes_hostile_agent_output() -> None:
    """A finding detail is arbitrary agent output. Rendered raw, it would make the report
    itself an XSS vector — the opposite of a security tool."""
    hostile = dict(GATE)
    hostile["failures"] = [
        {
            "check_type": "must_not_output",
            "severity": "critical",
            "detail": "<script>alert('xss')</script>",
            "category": "data_leakage",
        }
    ]
    html = render_html(
        build_report(
            agent_name="a",
            manifest=None,
            effective_policy=None,
            gate=hostile,
            risk=RISK,
            environment=None,
        )
    )
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_html_renders_an_allowed_verdict() -> None:
    allowed = {"decision": "allowed", "fingerprint": "fp", "reason": "All passed.", "failures": []}
    html = render_html(
        build_report(
            agent_name="Safe Bot",
            manifest=MANIFEST,
            effective_policy=None,
            gate=allowed,
            risk={"risk_level": "none"},
            environment="prod",
        )
    )
    assert "ALLOWED" in html
    assert "No findings" in html
