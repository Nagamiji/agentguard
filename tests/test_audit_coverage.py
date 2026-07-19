"""Observability Phase 1 — P0 audit coverage + request_id correlation.

Verifies that the security-impacting mutations now emit audit events (policy create,
policy version create, deploy-alias repoint), that the version dedupe path does NOT, and
that audit rows carry the request_id of the HTTP request that produced them. Needs Postgres.
"""

import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from keel.db import check_db
from keel.main import app

_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")

client = TestClient(app)


def _bootstrap() -> str:
    resp = client.post("/v1/orgs", json={"name": f"aud-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201, resp.text
    return str(resp.json()["api_key"])


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _events(key: str) -> list[dict[str, Any]]:
    resp = client.get("/v1/audit-events", headers=_auth(key))
    assert resp.status_code == 200, resp.text
    return list(resp.json())


def test_policy_creation_is_audited_and_correlates_by_request_id() -> None:
    key = _bootstrap()
    resp = client.post(
        "/v1/policies",
        json={"scope_type": "organization", "name": "baseline", "rules": {"max_tool_calls": 3}},
        headers=_auth(key),
    )
    assert resp.status_code == 201, resp.text
    request_id = resp.headers["X-Request-ID"]
    policy_id = resp.json()["policy"]["id"]

    created = [e for e in _events(key) if e["action"] == "policy.created"]
    assert len(created) == 1
    ev = created[0]
    assert ev["resource_type"] == "policy"
    assert ev["resource_id"] == policy_id
    # The audit row can be joined to the HTTP log line for the same request.
    assert ev["request_id"] == request_id
    assert ev["metadata"]["scope_type"] == "organization"
    assert ev["metadata"]["fingerprint"]


def test_policy_version_is_audited_but_dedupe_is_not() -> None:
    key = _bootstrap()
    policy_id = client.post(
        "/v1/policies",
        json={"scope_type": "organization", "name": "p", "rules": {"max_tool_calls": 3}},
        headers=_auth(key),
    ).json()["policy"]["id"]

    # A genuinely new version -> audited.
    v2 = client.post(
        f"/v1/policies/{policy_id}/versions",
        json={"rules": {"max_tool_calls": 9}},
        headers=_auth(key),
    )
    assert v2.status_code == 201, v2.text

    # Re-post identical rules -> dedupe 200, no new row, must NOT audit.
    dup = client.post(
        f"/v1/policies/{policy_id}/versions",
        json={"rules": {"max_tool_calls": 9}},
        headers=_auth(key),
    )
    assert dup.status_code == 200, dup.text

    version_events = [e for e in _events(key) if e["action"] == "policy.version_created"]
    assert len(version_events) == 1  # exactly one — the dedupe did not produce a second
    assert version_events[0]["metadata"]["sequence_number"] == 2
    assert version_events[0]["resource_id"] == policy_id


def test_alias_repoint_is_audited_with_previous_version() -> None:
    key = _bootstrap()
    agent_id = client.post(
        "/v1/agents", json={"name": f"a-{uuid.uuid4().hex[:6]}"}, headers=_auth(key)
    ).json()["id"]
    manifest = {
        "prompts": [{"role": "system", "content": "hi"}],
        "model": {"provider": "vertex", "id": "gemini-2.5-flash"},
        "tools": [],
    }
    version_id = client.post(
        f"/v1/agents/{agent_id}/versions", json={"manifest": manifest}, headers=_auth(key)
    ).json()["id"]

    # First set (create), then repoint (to the same version — still a pointer write).
    assert (
        client.put(
            f"/v1/agents/{agent_id}/aliases/prod",
            json={"version_id": version_id},
            headers=_auth(key),
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/v1/agents/{agent_id}/aliases/prod",
            json={"version_id": version_id},
            headers=_auth(key),
        ).status_code
        == 200
    )

    alias_events = [e for e in _events(key) if e["action"] == "agent.alias_set"]
    assert len(alias_events) == 2
    created = [e for e in alias_events if e["metadata"]["created"] is True]
    repointed = [e for e in alias_events if e["metadata"]["created"] is False]
    assert len(created) == 1 and len(repointed) == 1
    assert created[0]["metadata"]["previous_version_id"] is None
    assert repointed[0]["metadata"]["previous_version_id"] == version_id
    assert repointed[0]["metadata"]["alias_name"] == "prod"
    assert repointed[0]["resource_type"] == "agent_alias"
