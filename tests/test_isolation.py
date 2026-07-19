"""Integration tests: tenant isolation is enforced by Postgres RLS, not app code.

Requires a migrated database (`make up && make migrate`). Skipped locally when there is
no database; in CI (KEEL_REQUIRE_DB=1) a missing database is a failure, not a skip.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from keel.config import settings
from keel.db import check_db
from keel.main import app

# CI sets KEEL_REQUIRE_DB=1: a missing database there means the service container
# broke, and skipping would turn the tenant-isolation guarantee into a silent pass.
_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")

client = TestClient(app)


def _bootstrap(label: str) -> tuple[str, str]:
    resp = client.post("/v1/orgs", json={"name": f"{label}-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["organization"]["id"], body["api_key"]


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _upgrade_plan(org_id: str, plan: str = "pilot") -> None:
    """Move an org off the free plan (agent_limit=1) so multi-agent tests can run.

    These tests prove RLS isolation, not plan enforcement; the owner engine is used
    because there is no API for plan changes and the app role is RLS-scoped.
    """
    engine = create_engine(settings.migration_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE organizations "
                    "SET plan_id = (SELECT id FROM plans WHERE name = :plan) "
                    "WHERE id = :org_id"
                ),
                {"plan": plan, "org_id": org_id},
            )
    finally:
        engine.dispose()


def test_projects_are_isolated_between_tenants_by_rls() -> None:
    org_a, key_a = _bootstrap("org-a")
    org_b, key_b = _bootstrap("org-b")

    for key, name in ((key_a, "a-proj"), (key_b, "b-proj")):
        created = client.post("/v1/projects", json={"name": name}, headers=_auth(key))
        assert created.status_code == 201, created.text

    # The endpoint issues SELECT with NO organization filter — RLS must scope it.
    resp = client.get("/v1/projects", headers=_auth(key_a))
    assert resp.status_code == 200
    projects = resp.json()
    assert [p["name"] for p in projects] == ["a-proj"]
    assert {p["organization_id"] for p in projects} == {org_a}

    resp_b = client.get("/v1/projects", headers=_auth(key_b))
    assert [p["name"] for p in resp_b.json()] == ["b-proj"]
    assert {p["organization_id"] for p in resp_b.json()} == {org_b}


def test_missing_auth_is_rejected() -> None:
    assert client.get("/v1/projects").status_code == 401


def test_invalid_key_is_rejected() -> None:
    assert client.get("/v1/projects", headers=_auth("ag_not_a_real_key")).status_code == 401


def test_revoked_key_is_rejected() -> None:
    _, key = _bootstrap("org-revoke")
    issued = client.post(
        "/v1/orgs/keys", json={"name": "temp", "role": "viewer"}, headers=_auth(key)
    )
    assert issued.status_code == 201
    temp_key = issued.json()["api_key"]
    key_id = issued.json()["key"]["id"]

    assert client.get("/v1/projects", headers=_auth(temp_key)).status_code == 200
    assert client.delete(f"/v1/orgs/keys/{key_id}", headers=_auth(key)).status_code == 204
    assert client.get("/v1/projects", headers=_auth(temp_key)).status_code == 401


def test_cannot_revoke_another_orgs_key() -> None:
    _, key_a = _bootstrap("org-x")
    _, key_b = _bootstrap("org-y")
    issued = client.post(
        "/v1/orgs/keys", json={"name": "victim", "role": "viewer"}, headers=_auth(key_b)
    )
    victim_id = issued.json()["key"]["id"]

    resp = client.delete(f"/v1/orgs/keys/{victim_id}", headers=_auth(key_a))
    assert resp.status_code == 404  # not found *for this tenant*


# --- BE-02: the registry's three tables each need their own proof ------------------------
#
# RLS does not inherit through a foreign key. agent_versions and agent_aliases are children
# of agents, and a child table without its own policy leaks across tenants even when its
# parent is protected — so each table is tested separately rather than assumed safe.

_MANIFEST: dict[str, object] = {
    "prompts": [{"role": "system", "content": "You are a refund agent."}],
    "model": {"provider": "anthropic", "id": "claude-opus-4-8-20260115"},
    "params": {"temperature": 0.2},
}


def _make_agent(key: str, name: str) -> str:
    resp = client.post("/v1/agents", json={"name": name}, headers=_auth(key))
    assert resp.status_code == 201, resp.text
    agent_id: str = resp.json()["id"]
    return agent_id


def _make_version(key: str, agent_id: str, manifest: dict[str, object]) -> dict[str, object]:
    resp = client.post(
        f"/v1/agents/{agent_id}/versions", json={"manifest": manifest}, headers=_auth(key)
    )
    assert resp.status_code == 201, resp.text
    body: dict[str, object] = resp.json()
    return body


def test_agents_are_isolated_between_tenants_by_rls() -> None:
    org_a, key_a = _bootstrap("org-a")
    _org_b, key_b = _bootstrap("org-b")

    _make_agent(key_a, "a-agent")
    _make_agent(key_b, "b-agent")

    agents = client.get("/v1/agents", headers=_auth(key_a)).json()
    assert [a["name"] for a in agents] == ["a-agent"]
    assert {a["organization_id"] for a in agents} == {org_a}


def test_agent_versions_are_isolated_between_tenants_by_rls() -> None:
    _org_a, key_a = _bootstrap("org-a")
    _org_b, key_b = _bootstrap("org-b")

    agent_a = _make_agent(key_a, "a-agent")
    agent_b = _make_agent(key_b, "b-agent")
    _make_version(key_a, agent_a, _MANIFEST)
    _make_version(key_b, agent_b, _MANIFEST)

    versions = client.get(f"/v1/agents/{agent_a}/versions", headers=_auth(key_a)).json()
    assert len(versions) == 1

    # B's agent is invisible to A, so the whole path 404s rather than 403s: a 403 would
    # confirm the agent exists.
    assert client.get(f"/v1/agents/{agent_b}/versions", headers=_auth(key_a)).status_code == 404


def test_cross_tenant_agent_access_is_404_not_403() -> None:
    _org_a, key_a = _bootstrap("org-a")
    _org_b, key_b = _bootstrap("org-b")
    agent_b = _make_agent(key_b, "b-agent")

    assert client.get(f"/v1/agents/{agent_b}", headers=_auth(key_a)).status_code == 404
    assert (
        client.patch(
            f"/v1/agents/{agent_b}", json={"name": "hijacked"}, headers=_auth(key_a)
        ).status_code
        == 404
    )
    assert client.delete(f"/v1/agents/{agent_b}", headers=_auth(key_a)).status_code == 404


def test_alias_cannot_point_at_another_tenants_version() -> None:
    """The threat the FK alone does not stop.

    A tenant knowing another's version UUID must not be able to point its own alias at it.
    RLS makes that row invisible, so the lookup fails — but this is the assertion that says
    so out loud, because the failure would otherwise be silent and cross-tenant.
    """
    _org_a, key_a = _bootstrap("org-a")
    _org_b, key_b = _bootstrap("org-b")

    agent_a = _make_agent(key_a, "a-agent")
    agent_b = _make_agent(key_b, "b-agent")
    version_b = _make_version(key_b, agent_b, _MANIFEST)

    resp = client.put(
        f"/v1/agents/{agent_a}/aliases/production",
        json={"version_id": version_b["id"]},
        headers=_auth(key_a),
    )
    assert resp.status_code == 404, "a tenant must not alias another tenant's version"


def test_aliases_are_isolated_between_tenants_by_rls() -> None:
    _org_a, key_a = _bootstrap("org-a")
    _org_b, key_b = _bootstrap("org-b")

    agent_a = _make_agent(key_a, "a-agent")
    version_a = _make_version(key_a, agent_a, _MANIFEST)
    assert (
        client.put(
            f"/v1/agents/{agent_a}/aliases/production",
            json={"version_id": version_a["id"]},
            headers=_auth(key_a),
        ).status_code
        == 200
    )

    resolved = client.get(f"/v1/agents/{agent_a}/aliases/production", headers=_auth(key_a))
    assert resolved.status_code == 200
    # Resolution returns the concrete version, fingerprint included — MLflow #8078 is what
    # happens when a pin silently floats to latest.
    assert resolved.json()["fingerprint"] == version_a["fingerprint"]

    assert (
        client.get(f"/v1/agents/{agent_a}/aliases/production", headers=_auth(key_b)).status_code
        == 404
    )


# --- BE-02: registry behaviour that needs a real database --------------------------------


def test_identical_manifest_is_deduped_not_versioned_twice() -> None:
    """An unchanged config is not a new version (the gap langfuse#2161 asks for)."""
    _org_a, key_a = _bootstrap("org-a")
    agent = _make_agent(key_a, "dedup-agent")

    first = _make_version(key_a, agent, _MANIFEST)

    # Same manifest, reformatted: cosmetically different, behaviourally identical.
    noisy = dict(_MANIFEST)
    noisy["prompts"] = [{"role": "system", "content": "You are a refund agent.  \n\n"}]
    resp = client.post(
        f"/v1/agents/{agent}/versions", json={"manifest": noisy}, headers=_auth(key_a)
    )
    assert resp.status_code == 200, "a cosmetically-different manifest must dedupe, not create"
    assert resp.json()["id"] == first["id"]
    assert resp.json()["sequence_number"] == 1

    assert len(client.get(f"/v1/agents/{agent}/versions", headers=_auth(key_a)).json()) == 1


def test_changed_manifest_creates_a_new_version() -> None:
    _org_a, key_a = _bootstrap("org-a")
    agent = _make_agent(key_a, "seq-agent")

    _make_version(key_a, agent, _MANIFEST)
    changed = dict(_MANIFEST)
    changed["params"] = {"temperature": 0.9}
    second = _make_version(key_a, agent, changed)

    assert second["sequence_number"] == 2  # per agent, from 1


def test_sequence_numbers_are_per_agent_not_global() -> None:
    org_a, key_a = _bootstrap("org-a")
    _upgrade_plan(org_a)  # free plan caps at 1 agent; this test needs two
    agent_one = _make_agent(key_a, "agent-one")
    agent_two = _make_agent(key_a, "agent-two")

    assert _make_version(key_a, agent_one, _MANIFEST)["sequence_number"] == 1
    assert _make_version(key_a, agent_two, _MANIFEST)["sequence_number"] == 1


def test_manifest_with_a_secret_is_rejected() -> None:
    _org_a, key_a = _bootstrap("org-a")
    agent = _make_agent(key_a, "secret-agent")

    leaky = dict(_MANIFEST)
    leaky["prompts"] = [
        {"role": "system", "content": "Call the API with sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAA"}
    ]
    resp = client.post(
        f"/v1/agents/{agent}/versions", json={"manifest": leaky}, headers=_auth(key_a)
    )
    assert resp.status_code == 400
    # RFC-9457: an HTTPException's message surfaces as `title` (see keel/errors.py).
    assert "Anthropic API key" in resp.json()["title"]
    # The error names the credential type but must never echo the credential itself.
    assert "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAA" not in resp.text


def test_slug_is_unique_per_tenant_but_not_globally() -> None:
    org_a, key_a = _bootstrap("org-a")
    _org_b, key_b = _bootstrap("org-b")
    # The duplicate-slug attempt below must reach the slug check; on the free plan the
    # agent limit (1) fires first and turns the expected 409 into a 402.
    _upgrade_plan(org_a)

    assert (
        client.post("/v1/agents", json={"name": "Shared Name"}, headers=_auth(key_a)).status_code
        == 201
    )
    # Same slug in another tenant must be fine — a global constraint would leak the
    # existence of other orgs' agents through collisions.
    assert (
        client.post("/v1/agents", json={"name": "Shared Name"}, headers=_auth(key_b)).status_code
        == 201
    )
    # ...but a duplicate within one tenant is a conflict.
    assert (
        client.post("/v1/agents", json={"name": "Shared Name"}, headers=_auth(key_a)).status_code
        == 409
    )
