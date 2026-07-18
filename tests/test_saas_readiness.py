import os
import uuid

import pytest
from fastapi.testclient import TestClient

from keel.db import check_db
from keel.main import app

_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")

client = TestClient(app)


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_customer_onboarding_flow_and_agent_limit() -> None:
    # 1. Trigger onboarding
    org_name = f"acme-support-{uuid.uuid4().hex[:6]}"
    resp = client.post("/v1/onboarding", json={"organization_name": org_name})
    assert resp.status_code == 201
    body = resp.json()
    assert "organization_id" in body
    assert "api_key" in body
    assert "next_steps" in body
    assert body["api_key"].startswith("ag_")

    key = body["api_key"]

    # 2. Register first agent (should succeed on Free plan)
    resp_agent = client.post(
        "/v1/agents",
        json={"name": "Support Bot", "slug": f"bot-{uuid.uuid4().hex[:4]}"},
        headers=_auth(key),
    )
    assert resp_agent.status_code == 201

    # 3. Register second agent (should fail with 402 - Free limit is 1)
    resp_agent_fail = client.post(
        "/v1/agents",
        json={"name": "Second Bot", "slug": f"bot-{uuid.uuid4().hex[:4]}"},
        headers=_auth(key),
    )
    assert resp_agent_fail.status_code == 402
    # Problem Details envelope: the message lives in `title` / `error.message`,
    # not `detail` (src/keel/errors.py).
    body_fail = resp_agent_fail.json()
    assert "Agent limit reached" in body_fail["title"]
    assert body_fail["error"]["code"] == "PAYMENT_REQUIRED"
