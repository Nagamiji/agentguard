"""Policy validation, resolution, and compilation — pure, no DB."""

import pytest

from keel.policy import compile_policy, fingerprint_rules, resolve, validate_rules
from keel.policy.resolver import effective_values
from keel.policy.rules import PolicyError

MANIFEST = {
    "model": {"provider": "vertex", "id": "gemini-2.5-flash"},
    "tools": [{"name": "issue_refund"}, {"name": "delete_account"}],
}


# --- validation -------------------------------------------------------------------------


def test_valid_rules_pass() -> None:
    validate_rules(
        {
            "max_tool_arg": [{"tool": "issue_refund", "arg": "amount", "max": 100}],
            "forbidden_tools": ["delete_account"],
            "allowed_tools": ["issue_refund"],
            "max_tool_calls": 5,
            "allowed_providers": ["vertex"],
            "allowed_model_families": ["gemini"],
            "human_approval_required": True,  # runtime-declared, accepted
        }
    )


def test_an_unknown_rule_is_rejected_not_ignored() -> None:
    # A typo'd rule the customer thinks protects them must fail loudly.
    with pytest.raises(PolicyError, match="unknown rule 'max_refund'"):
        validate_rules({"max_refund": 100})


def test_empty_or_non_object_rules_are_rejected() -> None:
    with pytest.raises(PolicyError):
        validate_rules({})
    with pytest.raises(PolicyError):
        validate_rules(["not", "an", "object"])


def test_malformed_rule_values_are_rejected() -> None:
    with pytest.raises(PolicyError, match="numeric 'max'"):
        validate_rules({"max_tool_arg": [{"tool": "t", "arg": "a", "max": "lots"}]})
    with pytest.raises(PolicyError, match="integer"):
        validate_rules({"max_tool_calls": "five"})
    with pytest.raises(PolicyError, match="list of strings"):
        validate_rules({"forbidden_tools": "delete_account"})


def test_a_null_value_clears_a_rule_and_is_allowed() -> None:
    validate_rules({"max_tool_calls": None, "forbidden_tools": ["x"]})


def test_fingerprint_is_deterministic_and_key_order_independent() -> None:
    a = fingerprint_rules({"max_tool_calls": 5, "forbidden_tools": ["x"]})
    b = fingerprint_rules({"forbidden_tools": ["x"], "max_tool_calls": 5})
    assert a == b
    assert a != fingerprint_rules({"max_tool_calls": 6, "forbidden_tools": ["x"]})


# --- resolution + provenance ------------------------------------------------------------


def test_a_lower_scope_overrides_a_higher_one_and_records_the_source() -> None:
    resolved = resolve(
        [
            ("organization", {"max_tool_calls": 3}),
            ("agent", {"max_tool_calls": 10}),
        ]
    )
    assert resolved["max_tool_calls"].value == 10
    assert resolved["max_tool_calls"].source == "agent"  # provenance shows the override


def test_env_specific_overrides_env_agnostic_within_a_scope() -> None:
    # Caller passes agnostic then env-specific for the same scope; later wins.
    resolved = resolve(
        [
            ("organization", {"max_tool_calls": 3}),
            ("organization", {"max_tool_calls": 1}),
        ]
    )
    assert resolved["max_tool_calls"].value == 1


def test_a_null_at_a_lower_scope_clears_a_higher_rule() -> None:
    resolved = resolve(
        [("organization", {"forbidden_tools": ["x"]}), ("agent", {"forbidden_tools": None})]
    )
    assert "forbidden_tools" not in resolved


def test_effective_values_drops_provenance() -> None:
    resolved = resolve([("organization", {"max_tool_calls": 3})])
    assert effective_values(resolved) == {"max_tool_calls": 3}


# --- compilation ------------------------------------------------------------------------


def test_max_tool_arg_becomes_a_tool_arg_limit_check() -> None:
    compiled = compile_policy(
        {"max_tool_arg": [{"tool": "issue_refund", "arg": "amount", "max": 100}]}, MANIFEST
    )
    assert compiled.derived_checks == [
        {
            "type": "tool_arg_limit",
            "tool": "issue_refund",
            "arg": "amount",
            "max": 100,
            "category": "unsafe_tool_use",
            "severity": "critical",
        }
    ]


def test_forbidden_tool_yields_both_a_check_and_a_static_finding_when_declared() -> None:
    compiled = compile_policy({"forbidden_tools": ["delete_account"]}, MANIFEST)
    assert any(
        c["type"] == "must_not_call_tool" and c["tool"] == "delete_account"
        for c in compiled.derived_checks
    )
    # delete_account is declared in the manifest, so it is a static violation right now.
    assert any(
        f["check_type"] == "policy_forbidden_tool_declared" for f in compiled.manifest_findings
    )


def test_allowed_tools_forbids_everything_not_listed() -> None:
    compiled = compile_policy({"allowed_tools": ["issue_refund"]}, MANIFEST)
    # delete_account is not allow-listed -> a must_not_call check + a static finding.
    assert any(c["tool"] == "delete_account" for c in compiled.derived_checks)
    assert any(f["check_type"] == "policy_tool_not_allowed" for f in compiled.manifest_findings)
    # issue_refund IS allowed -> no check against it.
    assert not any(c.get("tool") == "issue_refund" for c in compiled.derived_checks)


def test_max_tool_calls_becomes_a_check() -> None:
    compiled = compile_policy({"max_tool_calls": 2}, MANIFEST)
    assert compiled.derived_checks == [
        {"type": "max_tool_calls", "max": 2, "category": "unsafe_tool_use", "severity": "high"}
    ]


def test_disallowed_provider_is_a_static_finding() -> None:
    compiled = compile_policy({"allowed_providers": ["anthropic"]}, MANIFEST)
    assert any(f["check_type"] == "policy_allowed_providers" for f in compiled.manifest_findings)
    # An allowed provider produces no finding.
    assert not compile_policy({"allowed_providers": ["vertex"]}, MANIFEST).manifest_findings


def test_model_family_is_matched_by_prefix() -> None:
    assert not compile_policy({"allowed_model_families": ["gemini"]}, MANIFEST).manifest_findings
    assert compile_policy({"allowed_model_families": ["claude"]}, MANIFEST).manifest_findings


def test_runtime_rules_are_deferred_not_enforced() -> None:
    compiled = compile_policy(
        {"human_approval_required": True, "geo_restrictions": ["EU"], "max_tool_calls": 3}, MANIFEST
    )
    assert set(compiled.deferred_runtime) == {"human_approval_required", "geo_restrictions"}
    # The deploy-enforceable rule still compiled.
    assert compiled.derived_checks
