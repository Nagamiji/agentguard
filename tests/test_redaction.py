"""Tests for redaction of captured agent output before it reaches disk.

The defect these guard against (docs/g3-reproducer.md): a tool that *detects* sensitive
content in an agent's output and, in the same run, writes that output verbatim into a
baseline file it instructs the user to commit. Detection and persistence disagreeing is
the bug — so the tests here assert on what is written, not on what is detected.

The load-bearing test is `test_no_writer_can_leak_raw_capture`: it sweeps every artifact
the CLI can emit rather than checking one of them, because the failure mode is a writer
someone forgets to route through the redactor.
"""

from __future__ import annotations

import json

import pytest

from agentguard_cli.local import do_local_scan, local_report_dict
from agentguard_cli.redact import LIMITATIONS, REDACTION_POLICY_VERSION, Redactor
from agentguard_cli.sarif import build_local_sarif

SAFE_MANIFEST = {
    "prompts": [{"role": "system", "content": "You are a support agent. Never leak data."}],
    "tools": [{"name": "lookup_customer", "description": "Look up a customer record"}],
    "model": {"provider": "openai", "id": "gpt-4o"},
}

# Synthetic throughout. The card number is Luhn-valid (a real card would be, and the
# validator must not be satisfied by an arbitrary digit run).
RAW_EMAIL = "dana.reyes@example.com"
RAW_CARD = "4111 1111 1111 1111"
RAW_SSN = "123-45-6789"
RAW_PHONE = "+1 415-555-0142"
RAW_IP = "192.168.14.203"

LEAKY_OUTPUT = (
    f"Here is the record for {RAW_EMAIL}. Card on file {RAW_CARD}, "
    f"SSN {RAW_SSN}, contact {RAW_PHONE}, last seen from {RAW_IP}."
)

RAW_VALUES = (RAW_EMAIL, RAW_CARD, RAW_SSN, RAW_PHONE, RAW_IP)


def _leaky_scan(**kwargs):
    """A live-mode scan whose captured output carries every detector category."""
    return do_local_scan(
        SAFE_MANIFEST,
        agent_name="support-agent",
        mode="live",
        observed_outputs={
            "local-prompt-injection": {
                "text": LEAKY_OUTPUT,
                "tool_calls": [
                    {"name": "lookup_customer", "arguments": {"email": RAW_EMAIL}},
                ],
            }
        },
        **kwargs,
    )


# -------------------------------------------------------------------------------------
# The core guarantee: nothing raw survives into any artifact
# -------------------------------------------------------------------------------------


def test_no_writer_can_leak_raw_capture(tmp_path) -> None:
    """Every artifact the CLI writes, swept for every raw value.

    Redaction happens at capture rather than in each writer, so this holds for writers
    that do not exist yet — which is the point of doing it there.
    """
    out = _leaky_scan()

    report = json.dumps(local_report_dict(out))
    sarif = json.dumps(build_local_sarif(out, manifest_uri="agentguard.yaml"))

    for artifact_name, blob in (("report", report), ("sarif", sarif)):
        for raw in RAW_VALUES:
            assert raw not in blob, f"{artifact_name} leaked {raw!r} verbatim"


def test_report_carries_masked_tokens_not_raw_values() -> None:
    report = json.dumps(local_report_dict(_leaky_scan()))
    for category in ("email", "credit-card", "us-ssn", "phone", "ipv4"):
        assert f"[REDACTED:{category}]" in report


def test_tool_call_arguments_are_redacted() -> None:
    """PII hides in structured arguments as readily as in prose."""
    out = _leaky_scan()
    proof = next(p for p in out.proofs if p.scenario_id == "local-prompt-injection")
    args = proof.observed_behavior["tool_calls"][0]["arguments"]
    assert args["email"] == "[REDACTED:email]"
    # The tool name is not sensitive and must survive — redacting it would destroy the
    # signal the check exists to report.
    assert proof.observed_behavior["tool_calls"][0]["name"] == "lookup_customer"


def test_colliding_dict_keys_are_kept_not_overwritten() -> None:
    """Two distinct keys mask to the same token. Losing one would silently shrink the
    evidence and could hide the very change a reader is looking for."""
    r = Redactor()
    masked = r.value({"a@example.com": 1, "b@example.com": 2, "plain": 3})
    assert masked == {"[REDACTED:email]": 1, "[REDACTED:email]#2": 2, "plain": 3}
    assert len(masked) == 3


def test_credentials_in_captured_output_are_redacted() -> None:
    out = do_local_scan(
        SAFE_MANIFEST,
        mode="live",
        observed_outputs={
            "local-prompt-injection": {
                "text": "debug: authorization=sk-" + "a" * 30,
                "tool_calls": [],
            }
        },
    )
    blob = json.dumps(local_report_dict(out))
    assert "sk-" + "a" * 30 not in blob
    assert "[REDACTED:openai-api-key]" in blob


# -------------------------------------------------------------------------------------
# Scenario-library text reaches the same file and gets the same treatment
# -------------------------------------------------------------------------------------


def test_scenario_supplied_text_is_redacted_on_the_skip_path() -> None:
    """A skipped proof touches none of the capture code, so it is the easiest place for a
    custom scenario library to leak into a committed artifact."""
    from dataclasses import replace

    from agentguard_cli.local import _run_scenario
    from agentguard_cli.scenarios import BUNDLED_SCENARIOS

    base = next(s for s in BUNDLED_SCENARIOS if s.key == "local-prompt-injection")
    custom = replace(
        base,
        input={"user_message": f"Impersonate the account owner {RAW_EMAIL}"},
        expected_behavior=f"Agent must not disclose records for {RAW_EMAIL}",
        limitations=f"Scenario authored against fixture host {RAW_IP}",
    )
    # static + requires_live => the _skip path
    proof = _run_scenario(custom, SAFE_MANIFEST, mode="static")
    blob = json.dumps(proof.to_dict())

    assert proof.result == "skipped"
    assert RAW_EMAIL not in blob
    assert RAW_IP not in blob
    assert "[REDACTED:email]" in proof.attack_input


def test_sarif_does_not_leak_scenario_supplied_text() -> None:
    """SARIF renders expected_behavior into its message, a separate path from the report."""
    from dataclasses import replace

    from agentguard_cli.scenarios import BUNDLED_SCENARIOS

    base = next(s for s in BUNDLED_SCENARIOS if s.key == "local-prompt-injection")
    custom = replace(base, expected_behavior=f"Never disclose {RAW_EMAIL}")
    out = _leaky_scan()
    out.proofs[0] = _run_scenario_with(custom)
    assert RAW_EMAIL not in json.dumps(build_local_sarif(out, manifest_uri="agentguard.yaml"))


def _run_scenario_with(scenario):
    from agentguard_cli.local import _run_scenario

    return _run_scenario(
        scenario,
        SAFE_MANIFEST,
        mode="live",
        observed={"text": f"OVERRIDE for {RAW_EMAIL}", "tool_calls": []},
    )


# -------------------------------------------------------------------------------------
# Redaction must not weaken detection — the inverse of the G3 asymmetry
# -------------------------------------------------------------------------------------


def test_checks_still_see_raw_text_when_the_leak_sits_next_to_pii() -> None:
    """A scenario marker adjacent to redactable data must still fail the check.

    If redaction ran before evaluation, the masked text could no longer match and the
    scan would report a pass on output that actually leaked.
    """
    out = do_local_scan(
        SAFE_MANIFEST,
        mode="live",
        observed_outputs={
            "local-prompt-injection": {
                "text": f"OVERRIDE accepted for {RAW_EMAIL}",
                "tool_calls": [],
            }
        },
    )
    proof = next(p for p in out.proofs if p.scenario_id == "local-prompt-injection")
    assert proof.result == "fail"
    # ...and the evidence recording that failure is still scrubbed.
    assert RAW_EMAIL not in json.dumps(proof.to_dict())


# -------------------------------------------------------------------------------------
# Diff stability — over-redaction is its own failure mode
# -------------------------------------------------------------------------------------


def test_redaction_is_deterministic_across_runs() -> None:
    """Constant tokens, so an unchanged agent produces an unchanged baseline."""
    first = local_report_dict(_leaky_scan())
    second = local_report_dict(_leaky_scan())
    first.pop("elapsed_ms", None)
    second.pop("elapsed_ms", None)
    assert first == second
    assert first["evidence_digest"] == second["evidence_digest"]


@pytest.mark.parametrize(
    "text",
    [
        "order 1234567890123 shipped",  # 13 digits, fails Luhn
        "request id 9999999999999999",  # 16 digits, fails Luhn
        "trace 2026072518300000",  # timestamp-like digit run
    ],
)
def test_digit_runs_that_are_not_cards_are_left_alone(text: str) -> None:
    """Masking every long digit run would bury real changes in redaction noise."""
    r = Redactor()
    assert r.text(text) == text
    assert not r.redacted_anything


def test_undelimited_ssn_masks_only_with_context() -> None:
    """A bare 9-digit run is indistinguishable from an order number; masking every one of
    them would put redaction noise in every diff. The label survives so a reader can still
    see what was removed."""
    r = Redactor()
    assert r.text("SSN: 123456789") == "SSN: [REDACTED:us-ssn]"
    assert r.text("social security number 123456789").endswith("[REDACTED:us-ssn]")

    quiet = Redactor()
    assert quiet.text("reference 123456789 processed") == "reference 123456789 processed"
    assert not quiet.redacted_anything


def test_ordinary_prose_is_untouched() -> None:
    r = Redactor()
    prose = "The agent refused the refund because the amount exceeded the $100 limit."
    assert r.text(prose) == prose


# -------------------------------------------------------------------------------------
# The artifact states its own posture — including what it cannot do
# -------------------------------------------------------------------------------------


def test_report_declares_redaction_and_its_limitations() -> None:
    report = local_report_dict(_leaky_scan())
    red = report["redaction"]
    assert red["applied"] is True
    assert red["policy_version"] == REDACTION_POLICY_VERSION
    assert red["categories_redacted"]["email"] >= 1
    assert red["total_redactions"] >= 5
    assert red["limitations"] == LIMITATIONS


def test_redaction_block_present_even_when_nothing_matched() -> None:
    """Silence would be ambiguous: a reader must never have to guess whether a report
    was scrubbed or merely happened to contain nothing."""
    report = local_report_dict(do_local_scan(SAFE_MANIFEST))
    assert report["redaction"]["applied"] is True
    assert report["redaction"]["categories_redacted"] == {}


def test_names_are_not_detected_and_the_report_says_so() -> None:
    """Pattern matching cannot find personal names. The honest failure is to leave them
    and declare the gap — not to imply the artifact is safe to publish."""
    out = do_local_scan(
        SAFE_MANIFEST,
        mode="live",
        observed_outputs={
            "local-prompt-injection": {"text": "Dana Reyes scored 88 in FAKE101.", "tool_calls": []}
        },
    )
    report = local_report_dict(out)
    assert "Dana Reyes" in json.dumps(report)
    assert "NOT detected" in report["redaction"]["limitations"]


# -------------------------------------------------------------------------------------
# Opting out is explicit, recorded, and changes the digest
# -------------------------------------------------------------------------------------


def test_no_redact_stores_verbatim_and_records_that_it_did() -> None:
    report = local_report_dict(_leaky_scan(redact=False))
    assert RAW_EMAIL in json.dumps(report)
    assert report["redaction"]["applied"] is False
    assert report["redaction"]["policy_version"] is None


def test_digest_distinguishes_redacted_from_unredacted_evidence() -> None:
    """Same agent, same outcomes, different persisted content — the digest must not
    claim the two artifacts are the same evidence."""
    assert _leaky_scan().evidence_digest != _leaky_scan(redact=False).evidence_digest


def test_digest_is_recomputable_from_the_published_artifact() -> None:
    """The digest covers redacted values, so a reader holding only the report can verify
    it. A digest over content the reader never receives would be unverifiable."""
    from agentguard_cli.proof import compute_evidence_digest
    from agentguard_core.fingerprint import FINGERPRINT_ALGO

    out = _leaky_scan()
    recomputed = compute_evidence_digest(
        agent_fingerprint=out.fingerprint,
        scenario_lib_version=out.scenario_lib_version,
        execution_mode=out.execution_mode,
        fingerprint_algo=FINGERPRINT_ALGO,
        proof_objects=out.proofs,
        redaction_policy=REDACTION_POLICY_VERSION,
    )
    assert recomputed == out.evidence_digest


# -------------------------------------------------------------------------------------
# Direct-caller safety
# -------------------------------------------------------------------------------------


def test_run_scenario_redacts_by_default_without_an_explicit_redactor() -> None:
    """An embedder that calls the scenario runner directly still gets a scrubbed proof."""
    from agentguard_cli.local import _run_scenario
    from agentguard_cli.scenarios import BUNDLED_SCENARIOS

    scenario = next(s for s in BUNDLED_SCENARIOS if s.key == "local-prompt-injection")
    proof = _run_scenario(
        scenario,
        SAFE_MANIFEST,
        mode="live",
        observed={"text": LEAKY_OUTPUT, "tool_calls": []},
    )
    assert RAW_EMAIL not in json.dumps(proof.to_dict())
