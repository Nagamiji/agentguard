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
    resp = client.post("/v1/orgs", json={"name": f"rbac-org-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201
    body = resp.json()
    return body["organization"]["id"], body["api_key"]


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_scopes_validation_on_key_creation() -> None:
    _, key = _bootstrap()
    # Invalid scope value should fail
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "test-key", "scopes": ["invalid_scope"]},
        headers=_auth(key),
    )
    assert resp.status_code == 422
    assert "Invalid scope" in resp.text


def test_rbac_scopes_enforcement() -> None:
    org_id, master_key = _bootstrap()

    # 1. Create a read-only key
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "read-key", "scopes": ["read"]},
        headers=_auth(master_key),
    )
    assert resp.status_code == 201
    read_key = resp.json()["api_key"]

    # 2. Create a write-only key
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "write-key", "scopes": ["write"]},
        headers=_auth(master_key),
    )
    assert resp.status_code == 201
    write_key = resp.json()["api_key"]

    # 3. Create a scan-only key
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "scan-key", "scopes": ["scan"]},
        headers=_auth(master_key),
    )
    assert resp.status_code == 201
    scan_key = resp.json()["api_key"]

    # Test READ permissions
    # A read-only key should succeed on GET
    assert client.get("/v1/agents", headers=_auth(read_key)).status_code == 200
    # A write-only key should be forbidden on GET
    assert client.get("/v1/agents", headers=_auth(write_key)).status_code == 403
    # A scan-only key should be forbidden on GET
    assert client.get("/v1/agents", headers=_auth(scan_key)).status_code == 403

    # Test WRITE permissions
    # A read-only key should be forbidden on POST
    resp_read = client.post("/v1/agents", json={"name": "Read Agent"}, headers=_auth(read_key))
    assert resp_read.status_code == 403
    # A write-only key should succeed on POST
    resp_write = client.post("/v1/agents", json={"name": "Write Agent"}, headers=_auth(write_key))
    assert resp_write.status_code == 201
    agent_id = resp_write.json()["id"]

    # Create agent version (needs write)
    manifest = {
        "prompts": [{"role": "system", "content": "Helpful bot"}],
        "model": {"provider": "vertex", "id": "gemini-2.5-flash"},
        "tools": [],
    }
    resp_version = client.post(
        f"/v1/agents/{agent_id}/versions",
        json={"manifest": manifest},
        headers=_auth(write_key),
    )
    assert resp_version.status_code == 201
    version_id = resp_version.json()["id"]
    fingerprint = resp_version.json()["fingerprint"]

    # Test SCAN permissions (evaluation)
    # A read-only key should be forbidden on runs
    resp_run_read = client.post(
        f"/v1/agents/{agent_id}/runs",
        json={"version_id": version_id, "runner": "scripted"},
        headers=_auth(read_key),
    )
    assert resp_run_read.status_code == 403

    # A scan-only key should succeed on runs
    resp_run_scan = client.post(
        f"/v1/agents/{agent_id}/runs",
        json={"version_id": version_id, "runner": "scripted"},
        headers=_auth(scan_key),
    )
    assert resp_run_scan.status_code == 201

    # A scan-only key should succeed on gate and risk
    assert (
        client.get(
            f"/v1/agents/{agent_id}/gate?fingerprint={fingerprint}",
            headers=_auth(scan_key),
        ).status_code
        == 200
    )

    assert (
        client.get(
            f"/v1/agents/{agent_id}/risk?fingerprint={fingerprint}",
            headers=_auth(scan_key),
        ).status_code
        == 200
    )

    # Test ADMIN permissions (keys endpoints)
    # Only master key (default wildcard '*' scope) or admin key can manage keys
    # Read/Write/Scan keys should not be able to issue keys
    assert (
        client.post(
            "/v1/orgs/keys",
            json={"name": "key-by-read", "scopes": ["read"]},
            headers=_auth(read_key),
        ).status_code
        == 403
    )

    # Master key can issue keys
    assert (
        client.post(
            "/v1/orgs/keys",
            json={"name": "key-by-master", "scopes": ["read"]},
            headers=_auth(master_key),
        ).status_code
        == 201
    )
