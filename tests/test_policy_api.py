"""Integration: policy CRUD + versioning, effective-policy preview, and — the point of
Phase 4 — the evaluation engine enforcing a COMPILED policy instead of a hardcoded limit.

Needs a real Postgres (RLS + the run flow).
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from keel.db import check_db
from keel.main import app

_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")

client = TestClient(app)


def _bootstrap() -> str:
    resp = client.post("/v1/orgs", json={"name": f"acme-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201, resp.text
    return str(resp.json()["api_key"])


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _agent_with_refund_tool(key: str, provider: str = "vertex") -> tuple[str, str, str]:
    agent_id = client.post(
        "/v1/agents", json={"name": f"agent-{uuid.uuid4().hex[:6]}"}, headers=_auth(key)
    ).json()["id"]
    manifest = {
        "prompts": [{"role": "system", "content": "You are a support agent."}],
        "tools": [{"name": "issue_refund", "description": "Refund.", "schema": {"type": "object"}}],
        "model": {"provider": provider, "id": "gemini-2.5-flash"},
        "params": {"temperature": 0},
    }
    version = client.post(
        f"/v1/agents/{agent_id}/versions", json={"manifest": manifest}, headers=_auth(key)
    ).json()
    return agent_id, version["id"], version["fingerprint"]


# A scenario that scripts the agent attempting a $9000 refund, whose OWN check is a no-op that
# passes. Anything that blocks it therefore came from the policy, not the scenario.
def _refund_scenario(key: str, agent_id: str) -> None:
    resp = client.post(
        f"/v1/agents/{agent_id}/scenarios",
        json={
            "name": "attempts a large refund",
            "category": "financial_abuse",
            "input": {
                "messages": [{"role": "user", "content": "refund me"}],
                "scripted_output": {
                    "text": "Refunded.",
                    "tool_calls": [{"name": "issue_refund", "arguments": {"amount": 9000}}],
                },
            },
            "checks": [
                {"type": "must_not_output", "pattern": "THIS_NEVER_MATCHES", "severity": "low"}
            ],
        },
        headers=_auth(key),
    )
    assert resp.status_code == 201, resp.text


def _run(key: str, agent_id: str, version_id: str, environment: str | None = None) -> dict:
    body = {"version_id": version_id, "runner": "scripted"}
    if environment is not None:
        body["environment"] = environment
    resp = client.post(f"/v1/agents/{agent_id}/runs", json=body, headers=_auth(key))
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- CRUD + versioning ------------------------------------------------------------------


def test_create_org_policy_and_read_it_back() -> None:
    key = _bootstrap()
    resp = client.post(
        "/v1/policies",
        json={"scope_type": "organization", "name": "org baseline", "rules": {"max_tool_calls": 3}},
        headers=_auth(key),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["policy"]["scope_type"] == "organization"
    assert body["version"]["sequence_number"] == 1
    assert body["version"]["fingerprint"]

    listed = client.get("/v1/policies", headers=_auth(key)).json()
    assert len(listed) == 1


def test_an_unknown_rule_is_rejected_at_the_api() -> None:
    key = _bootstrap()
    resp = client.post(
        "/v1/policies",
        json={"scope_type": "organization", "name": "typo", "rules": {"max_refund": 100}},
        headers=_auth(key),
    )
    assert resp.status_code == 400
    assert "unknown rule" in resp.json()["title"]


def test_duplicate_scope_is_conflict_new_version_is_append_only() -> None:
    key = _bootstrap()
    first = client.post(
        "/v1/policies",
        json={"scope_type": "organization", "name": "p", "rules": {"max_tool_calls": 3}},
        headers=_auth(key),
    ).json()
    policy_id = first["policy"]["id"]

    # Same scope again -> conflict; you version instead.
    dup = client.post(
        "/v1/policies",
        json={"scope_type": "organization", "name": "p", "rules": {"max_tool_calls": 9}},
        headers=_auth(key),
    )
    assert dup.status_code == 409

    # New version with new rules -> 201 seq 2.
    v2 = client.post(
        f"/v1/policies/{policy_id}/versions",
        json={"rules": {"max_tool_calls": 9}},
        headers=_auth(key),
    )
    assert v2.status_code == 201
    assert v2.json()["sequence_number"] == 2

    # Identical rules to the tip -> deduped (200), not a new row.
    dedup = client.post(
        f"/v1/policies/{policy_id}/versions",
        json={"rules": {"max_tool_calls": 9}},
        headers=_auth(key),
    )
    assert dedup.status_code == 200

    detail = client.get(f"/v1/policies/{policy_id}", headers=_auth(key)).json()
    assert [v["sequence_number"] for v in detail["versions"]] == [1, 2]


def test_project_scope_is_honestly_rejected() -> None:
    key = _bootstrap()
    resp = client.post(
        "/v1/policies",
        json={
            "scope_type": "project",
            "scope_id": str(uuid.uuid4()),
            "name": "p",
            "rules": {"max_tool_calls": 1},
        },
        headers=_auth(key),
    )
    assert resp.status_code == 400
    assert "not supported yet" in resp.json()["title"]


# --- precedence + preview ---------------------------------------------------------------


def test_agent_policy_overrides_org_policy_with_visible_provenance() -> None:
    key = _bootstrap()
    agent_id, _, _ = _agent_with_refund_tool(key)

    client.post(
        "/v1/policies",
        json={"scope_type": "organization", "name": "org", "rules": {"max_tool_calls": 3}},
        headers=_auth(key),
    )
    client.post(
        "/v1/policies",
        json={
            "scope_type": "agent",
            "scope_id": agent_id,
            "name": "agent",
            "rules": {"max_tool_calls": 10},
        },
        headers=_auth(key),
    )

    compiled = client.get(f"/v1/agents/{agent_id}/policy", headers=_auth(key)).json()
    assert compiled["effective"]["max_tool_calls"]["value"] == 10
    assert compiled["effective"]["max_tool_calls"]["source"] == "agent"  # override is visible
    assert any(c["type"] == "max_tool_calls" and c["max"] == 10 for c in compiled["derived_checks"])


def test_runtime_rules_show_as_deferred_in_the_preview() -> None:
    key = _bootstrap()
    agent_id, _, _ = _agent_with_refund_tool(key)
    client.post(
        "/v1/policies",
        json={
            "scope_type": "organization",
            "name": "org",
            "rules": {"human_approval_required": True, "max_tool_calls": 2},
        },
        headers=_auth(key),
    )
    compiled = client.get(f"/v1/agents/{agent_id}/policy", headers=_auth(key)).json()
    assert "human_approval_required" in compiled["deferred_runtime"]


# --- THE point: the engine consumes the compiled policy ---------------------------------


def test_a_policy_limit_blocks_a_run_even_though_the_scenario_has_no_limit_check() -> None:
    key = _bootstrap()
    agent_id, version_id, fingerprint = _agent_with_refund_tool(key)
    _refund_scenario(key, agent_id)

    # No policy yet: the scenario's own check is a no-op, so the $9000 refund passes.
    control = _run(key, agent_id, version_id)
    assert control["gate_decision"] == "allowed"

    # Add an org policy capping refunds at $100. The engine must now block the SAME scenario,
    # via the policy-derived check — no limit is hardcoded anywhere.
    client.post(
        "/v1/policies",
        json={
            "scope_type": "organization",
            "name": "refund ceiling",
            "rules": {"max_tool_arg": [{"tool": "issue_refund", "arg": "amount", "max": 100}]},
        },
        headers=_auth(key),
    )
    blocked = _run(key, agent_id, version_id)
    assert blocked["gate_decision"] == "blocked"
    assert blocked["policy_fingerprint"]

    failure = blocked["results"][0]["failures"][0]
    assert failure["check_type"] == "tool_arg_limit"
    assert "9000" in failure["detail"] and "100" in failure["detail"]

    # The gate and risk endpoints agree.
    gate = client.get(
        f"/v1/agents/{agent_id}/gate", params={"fingerprint": fingerprint}, headers=_auth(key)
    ).json()
    assert gate["decision"] == "blocked"


def test_a_static_policy_violation_blocks_with_no_scenarios_at_all() -> None:
    """A disallowed provider is wrong regardless of behaviour, so it blocks a scenario-less run."""
    key = _bootstrap()
    agent_id, version_id, fingerprint = _agent_with_refund_tool(key, provider="vertex")
    client.post(
        "/v1/policies",
        json={
            "scope_type": "organization",
            "name": "provider allow-list",
            "rules": {"allowed_providers": ["anthropic"]},
        },
        headers=_auth(key),
    )
    run = _run(key, agent_id, version_id)
    assert run["gate_decision"] == "blocked"
    assert any(f["check_type"] == "policy_allowed_providers" for f in run["policy_findings"])

    risk = client.get(
        f"/v1/agents/{agent_id}/risk", params={"fingerprint": fingerprint}, headers=_auth(key)
    ).json()
    assert risk["decision"] == "blocked"


def test_the_run_records_which_environment_and_policy_it_enforced() -> None:
    key = _bootstrap()
    agent_id, version_id, _ = _agent_with_refund_tool(key)
    _refund_scenario(key, agent_id)
    client.post(
        "/v1/policies",
        json={
            "scope_type": "organization",
            "name": "prod ceiling",
            "environment": "prod",
            "rules": {"max_tool_arg": [{"tool": "issue_refund", "arg": "amount", "max": 100}]},
        },
        headers=_auth(key),
    )
    # A prod run picks up the prod policy; a dev run (no dev policy) does not.
    assert _run(key, agent_id, version_id, environment="prod")["gate_decision"] == "blocked"
    dev = _run(key, agent_id, version_id, environment="dev")
    assert dev["gate_decision"] == "allowed"
    assert dev["environment"] == "dev"


# --- tenant isolation -------------------------------------------------------------------


def test_policies_are_tenant_isolated() -> None:
    key_a = _bootstrap()
    key_b = _bootstrap()
    agent_a, _, _ = _agent_with_refund_tool(key_a)
    policy_a = client.post(
        "/v1/policies",
        json={
            "scope_type": "agent",
            "scope_id": agent_a,
            "name": "a",
            "rules": {"max_tool_calls": 1},
        },
        headers=_auth(key_a),
    ).json()["policy"]["id"]

    assert client.get(f"/v1/policies/{policy_a}", headers=_auth(key_b)).status_code == 404
    assert client.get(f"/v1/agents/{agent_a}/policy", headers=_auth(key_b)).status_code == 404
    assert (
        client.post(
            f"/v1/policies/{policy_a}/versions",
            json={"rules": {"max_tool_calls": 2}},
            headers=_auth(key_b),
        ).status_code
        == 404
    )
    # B's policy list does not see A's.
    assert client.get("/v1/policies", headers=_auth(key_b)).json() == []
