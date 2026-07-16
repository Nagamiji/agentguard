"""The built-in attack library must be internally consistent — no DB, no model.

If the library ships a broken probe, every customer inherits the bug, so these invariants
are asserted at build time: a probe that never fires would report a pass for something never
actually tested, which is the worst failure this product can have.
"""

import json

import pytest

from keel.evals.checks import Severity, validate_checks
from keel.evals.library import (
    LIBRARY,
    LIBRARY_VERSION,
    all_scenarios,
    concrete_input,
    scenarios_for,
)
from keel.evals.taxonomy import ScenarioCategory


def test_library_is_non_empty_and_versioned() -> None:
    assert all_scenarios()
    assert LIBRARY_VERSION


def test_every_scenario_has_valid_checks() -> None:
    # validate_checks is what the API runs on customer scenarios; the corpus must clear the
    # same bar or an import would seed an un-runnable scenario.
    for s in LIBRARY:
        validate_checks(s.checks)


def test_scenario_keys_are_unique() -> None:
    keys = [s.key for s in LIBRARY]
    assert len(keys) == len(set(keys))


def test_every_category_and_severity_is_from_the_taxonomy() -> None:
    for s in LIBRARY:
        assert isinstance(s.category, ScenarioCategory)
        assert isinstance(s.severity, Severity)


def test_every_planted_marker_is_actually_present_in_the_input() -> None:
    """A must_not_output probe is only real if the marker it forbids is planted where the
    agent can reach it. This catches a copy-paste drift between the check and the attack."""
    for s in LIBRARY:
        blob = json.dumps(concrete_input(s, ["lookup_order"]))
        for check in s.checks:
            if check["type"] == "must_not_output":
                assert check["pattern"] in blob, f"{s.key}: forbidden marker not planted in input"


def test_universal_scenarios_carry_no_tool_specific_state() -> None:
    # A universal probe must run against any agent, so it cannot bake in tool_results.
    for s in LIBRARY:
        if not s.requires_tools:
            assert "tool_results" not in s.input, f"{s.key} is universal but pins tool_results"


def test_tool_scenarios_are_dropped_for_a_toolless_agent() -> None:
    with_tools = {s.key for s in scenarios_for(["issue_refund"])}
    without_tools = {s.key for s in scenarios_for([])}
    tool_only = with_tools - without_tools
    assert tool_only, "expected at least one tool-requiring probe"
    assert all(s.requires_tools for s in LIBRARY if s.key in tool_only)


def test_concrete_input_injects_the_marker_into_every_declared_tool() -> None:
    tool_scenario = next(s for s in LIBRARY if s.fill_tool_results)
    materialised = concrete_input(tool_scenario, ["lookup_order", "issue_refund"])
    results = materialised["tool_results"]
    assert set(results) == {"lookup_order", "issue_refund"}
    # Whichever tool the model calls, it receives the poisoned result.
    for payload in results.values():
        assert "KEEL-TOOLRESULT-LEAK" in json.dumps(payload)


def test_high_value_categories_are_covered() -> None:
    covered = {s.category for s in LIBRARY}
    for required in (
        ScenarioCategory.PROMPT_INJECTION,
        ScenarioCategory.DATA_EXFILTRATION,
        ScenarioCategory.PRIVILEGE_ESCALATION,
        ScenarioCategory.FINANCIAL_ABUSE,
    ):
        assert required in covered, f"library must probe {required}"


def test_hallucinated_action_is_a_known_gap_not_a_silent_one() -> None:
    """The taxonomy names hallucinated_action but v1 ships no probe for it (needs a check
    type we do not have). This test encodes the gap on purpose: adding a probe should make
    someone update this assertion deliberately, not discover it by surprise."""
    covered = {s.category for s in LIBRARY}
    assert ScenarioCategory.HALLUCINATED_ACTION not in covered


@pytest.mark.parametrize("scenario", LIBRARY, ids=lambda s: s.key)
def test_each_scenario_has_a_description_and_attack_summary(scenario: object) -> None:
    # These land in the risk report a customer reads; empty strings would make it useless.
    assert scenario.title and scenario.description and scenario.attack  # type: ignore[attr-defined]
