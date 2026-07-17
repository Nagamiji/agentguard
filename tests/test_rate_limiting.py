import os
import uuid

import pytest
from fastapi.testclient import TestClient

from keel.config import settings
from keel.db import check_db, get_redis_client
from keel.main import app

_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")

client = TestClient(app)


def _bootstrap() -> tuple[str, str]:
    resp = client.post("/v1/orgs", json={"name": f"limit-org-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201
    body = resp.json()
    return body["organization"]["id"], body["api_key"]


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_rate_limiting_enforcement() -> None:
    # 1. Enable rate limiting for this test
    original_enabled = settings.rate_limit_enabled
    settings.rate_limit_enabled = True
    original_scans = settings.rate_limit_scans_per_minute
    original_burst = settings.rate_limit_scans_burst

    # Configure very low scan limit for testing: 60/min (1/sec), burst 1
    settings.rate_limit_scans_per_minute = 60
    settings.rate_limit_scans_burst = 1

    try:
        org_id, key = _bootstrap()

        # Clear redis rate limit state to start fresh
        redis_client = get_redis_client()
        redis_client.delete(f"rate_limit:{org_id}:scans")

        # Create mock agent and version to call scan endpoint
        resp_agent = client.post("/v1/agents", json={"name": "Limiter Agent"}, headers=_auth(key))
        assert resp_agent.status_code == 201
        agent_id = resp_agent.json()["id"]

        manifest = {
            "prompts": [{"role": "system", "content": "Helpful bot"}],
            "model": {"provider": "vertex", "id": "gemini-2.5-flash"},
            "tools": [],
        }
        resp_version = client.post(
            f"/v1/agents/{agent_id}/versions",
            json={"manifest": manifest},
            headers=_auth(key),
        )
        assert resp_version.status_code == 201
        version_id = resp_version.json()["id"]

        # Call run endpoint once: should succeed
        resp_run1 = client.post(
            f"/v1/agents/{agent_id}/runs",
            json={"version_id": version_id, "runner": "scripted"},
            headers=_auth(key),
        )
        assert resp_run1.status_code == 201

        # Call run endpoint immediately again: should be rate-limited (429)
        resp_run2 = client.post(
            f"/v1/agents/{agent_id}/runs",
            json={"version_id": version_id, "runner": "scripted"},
            headers=_auth(key),
        )
        assert resp_run2.status_code == 429
        assert "Retry-After" in resp_run2.headers
        assert "Rate limit exceeded" in resp_run2.json()["title"]

    finally:
        # Restore configuration settings
        settings.rate_limit_enabled = original_enabled
        settings.rate_limit_scans_per_minute = original_scans
        settings.rate_limit_scans_burst = original_burst
