import os
import uuid

import pytest
from fastapi.testclient import TestClient

from keel.db import check_db
from keel.main import app

_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")

client = TestClient(app)


def _bootstrap() -> tuple[str, str]:
    resp = client.post("/v1/orgs", json={"name": f"dash-org-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201
    body = resp.json()
    return body["organization"]["id"], body["api_key"]


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_dashboard_console_served() -> None:
    # GET /dashboard should return HTML
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "AgentGuard Security Console" in resp.text

    # GET / should redirect to /dashboard
    resp_redirect = client.get("/", follow_redirects=False)
    assert resp_redirect.status_code == 307
    assert resp_redirect.headers["location"] == "/dashboard"


def test_runs_list_endpoint_and_rls_isolation() -> None:
    # 1. Bootstrap Org A
    org_a_id, key_a = _bootstrap()
    # 2. Bootstrap Org B
    org_b_id, key_b = _bootstrap()

    # Create agent and run for Org A
    resp_agent_a = client.post("/v1/agents", json={"name": "Agent A"}, headers=_auth(key_a))
    assert resp_agent_a.status_code == 201
    agent_a_id = resp_agent_a.json()["id"]

    manifest = {
        "prompts": [{"role": "system", "content": "Helpful bot"}],
        "model": {"provider": "vertex", "id": "gemini-2.5-flash"},
        "tools": [],
    }
    resp_version_a = client.post(
        f"/v1/agents/{agent_a_id}/versions",
        json={"manifest": manifest},
        headers=_auth(key_a),
    )
    assert resp_version_a.status_code == 201
    version_a_id = resp_version_a.json()["id"]

    resp_run_a = client.post(
        f"/v1/agents/{agent_a_id}/runs",
        json={"version_id": version_a_id, "runner": "scripted"},
        headers=_auth(key_a),
    )
    assert resp_run_a.status_code == 201
    run_a_id = resp_run_a.json()["id"]

    # Retrieve runs with key A
    runs_a = client.get("/v1/runs", headers=_auth(key_a)).json()
    assert len(runs_a) >= 1
    # Check that our run is in the list
    assert any(r["id"] == run_a_id for r in runs_a)

    # Retrieve runs with key B: should NOT see Org A's run (RLS Isolation)
    runs_b = client.get("/v1/runs", headers=_auth(key_b)).json()
    assert not any(r["id"] == run_a_id for r in runs_b)
