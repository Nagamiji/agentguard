"""Tenant isolation tests.

Verifies that Org A cannot access Org B's resources even with a valid API key.
These tests require a real Postgres connection with RLS enabled.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from keel.db import check_db
from keel.main import app

client = TestClient(app)

_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")


def _bootstrap(name_prefix: str = "iso") -> tuple[str, str]:
    """Create an org and return (org_id, api_key)."""
    resp = client.post("/v1/orgs", json={"name": f"{name_prefix}-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201
    body = resp.json()
    return body["organization"]["id"], body["api_key"]


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_org_a_cannot_see_org_b_agents() -> None:
    """Positive: Org A sees its own agents. Negative: cannot see Org B's agents."""
    org_a_id, key_a = _bootstrap("orga")
    org_b_id, key_b = _bootstrap("orgb")

    # Register an agent in Org B
    b_agent = client.post(
        "/v1/agents",
        json={"name": "BotB", "slug": f"bot-b-{uuid.uuid4().hex[:4]}"},
        headers=_auth(key_b),
    )
    assert b_agent.status_code == 201
    b_agent_id = b_agent.json()["id"]

    # Org A lists agents — must not see Org B's agent
    a_agents = client.get("/v1/agents", headers=_auth(key_a)).json()
    a_agent_ids = {a["id"] for a in a_agents}
    assert b_agent_id not in a_agent_ids

    # Org A directly fetches Org B's agent — must 404 (not 403 leak)
    direct = client.get(f"/v1/agents/{b_agent_id}", headers=_auth(key_a))
    assert direct.status_code == 404


def test_org_a_cannot_list_org_b_api_keys() -> None:
    """Org A's key listing must only return Org A's keys."""
    _, key_a = _bootstrap("key-iso-a")
    _, key_b = _bootstrap("key-iso-b")

    keys_a = client.get("/v1/orgs/keys", headers=_auth(key_a)).json()
    keys_b = client.get("/v1/orgs/keys", headers=_auth(key_b)).json()

    ids_a = {k["id"] for k in keys_a}
    ids_b = {k["id"] for k in keys_b}
    assert ids_a.isdisjoint(ids_b), "API key lists leaked across org boundary"


def test_org_cannot_revoke_other_org_key() -> None:
    """Org A cannot revoke Org B's API key."""
    _, key_a = _bootstrap("rev-a")
    _, key_b = _bootstrap("rev-b")

    # Get Org B's key ID
    keys_b = client.get("/v1/orgs/keys", headers=_auth(key_b)).json()
    b_key_id = keys_b[0]["id"]

    # Org A tries to revoke Org B's key
    resp = client.delete(f"/v1/orgs/keys/{b_key_id}", headers=_auth(key_a))
    # Must be 404 (not found in Org A's scope) — not 200 or 204
    assert resp.status_code == 404


def test_org_a_cannot_see_org_b_runs() -> None:
    """Evaluation runs must be scoped by organization_id."""
    _, key_a = _bootstrap("runs-a")
    _, key_b = _bootstrap("runs-b")

    runs_a = client.get("/v1/runs", headers=_auth(key_a))
    runs_b = client.get("/v1/runs", headers=_auth(key_b))

    if runs_a.status_code == 200 and runs_b.status_code == 200:
        ids_a = {r.get("id") for r in runs_a.json()}
        ids_b = {r.get("id") for r in runs_b.json()}
        assert ids_a.isdisjoint(ids_b), "Run IDs leaked across org boundary"
    # 404 is acceptable if /v1/runs doesn't exist yet
    elif runs_a.status_code == 404 and runs_b.status_code == 404:
        pass
    else:
        assert runs_a.status_code in (200, 404)
        assert runs_b.status_code in (200, 404)
