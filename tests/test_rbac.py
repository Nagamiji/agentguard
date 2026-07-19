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


# --- Phase 15: role presets, key expiry, lifecycle metadata, audit trail ----------------


def test_role_preset_expands_to_scopes_and_enforces() -> None:
    _, master_key = _bootstrap()

    # A 'ci' role key: can run scans and read, but cannot manage agents or keys.
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "gh-actions", "role": "ci"},
        headers=_auth(master_key),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["key"]
    assert body["role"] == "ci"
    assert sorted(body["scopes"]) == ["read", "scan"]
    assert body["status"] == "active"
    ci_key = resp.json()["api_key"]

    # read works, write does not (no 'write' scope), key management does not (no 'admin').
    assert client.get("/v1/agents", headers=_auth(ci_key)).status_code == 200
    assert client.post("/v1/agents", json={"name": "x"}, headers=_auth(ci_key)).status_code == 403
    assert (
        client.post(
            "/v1/orgs/keys", json={"name": "n", "role": "viewer"}, headers=_auth(ci_key)
        ).status_code
        == 403
    )


def test_role_and_scopes_are_mutually_exclusive() -> None:
    _, master_key = _bootstrap()
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "bad", "role": "ci", "scopes": ["read"]},
        headers=_auth(master_key),
    )
    assert resp.status_code == 422
    assert "either 'role' or 'scopes'" in resp.text


def test_invalid_role_is_rejected() -> None:
    _, master_key = _bootstrap()
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "bad", "role": "superuser"},
        headers=_auth(master_key),
    )
    assert resp.status_code == 422
    assert "Invalid role" in resp.text


def test_expired_key_is_rejected() -> None:
    _, master_key = _bootstrap()
    # Mint a key and force its expiry into the past directly in the DB, since the API only
    # accepts future expiries (expires_in_days >= 1).
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "short-lived", "role": "viewer", "expires_in_days": 1},
        headers=_auth(master_key),
    )
    assert resp.status_code == 201
    key_id = resp.json()["key"]["id"]
    short_key = resp.json()["api_key"]

    # Still valid right now.
    assert client.get("/v1/agents", headers=_auth(short_key)).status_code == 200

    from datetime import UTC, datetime, timedelta

    from sqlalchemy import create_engine, text

    from keel.config import settings

    engine = create_engine(settings.migration_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE api_keys SET expires_at = :t WHERE id = :id"),
                {"t": datetime.now(UTC) - timedelta(seconds=1), "id": key_id},
            )
    finally:
        engine.dispose()

    resp_after = client.get("/v1/agents", headers=_auth(short_key))
    assert resp_after.status_code == 401
    assert "expired" in resp_after.text.lower()


def test_last_used_at_is_recorded() -> None:
    _, master_key = _bootstrap()
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "tracked", "role": "viewer"},
        headers=_auth(master_key),
    )
    key_id = resp.json()["key"]["id"]
    tracked = resp.json()["api_key"]
    assert resp.json()["key"]["last_used_at"] is None

    assert client.get("/v1/agents", headers=_auth(tracked)).status_code == 200

    keys = client.get("/v1/orgs/keys", headers=_auth(master_key)).json()
    tracked_row = next(k for k in keys if k["id"] == key_id)
    assert tracked_row["last_used_at"] is not None
    assert tracked_row["created_by"] is not None  # the master key that issued it


def test_audit_trail_records_key_lifecycle() -> None:
    _, master_key = _bootstrap()

    issued = client.post(
        "/v1/orgs/keys",
        json={"name": "audited", "role": "developer"},
        headers=_auth(master_key),
    )
    new_id = issued.json()["key"]["id"]
    assert client.delete(f"/v1/orgs/keys/{new_id}", headers=_auth(master_key)).status_code == 204

    events = client.get("/v1/audit-events", headers=_auth(master_key))
    assert events.status_code == 200
    actions = [e["action"] for e in events.json()]
    assert "api_key.issued" in actions
    assert "api_key.revoked" in actions


def test_audit_trail_is_tenant_isolated() -> None:
    _, key_a = _bootstrap()
    _, key_b = _bootstrap()

    # A creates a key -> an audit event in A's trail.
    client.post("/v1/orgs/keys", json={"name": "a-key", "role": "viewer"}, headers=_auth(key_a))

    events_b = client.get("/v1/audit-events", headers=_auth(key_b)).json()
    assert all(e["action"] != "api_key.issued" or e["actor"] != key_a[:12] for e in events_b)
    # B's brand-new org has no key-issue events from A.
    assert events_b == [] or all("a-key" not in str(e.get("metadata", {})) for e in events_b)


def test_roles_catalog_endpoint() -> None:
    _, key = _bootstrap()
    resp = client.get("/v1/roles", headers=_auth(key))
    assert resp.status_code == 200
    roles = resp.json()
    assert roles["ci"] == ["read", "scan"]
    assert roles["owner"] == ["*"]


# --- Key-scope hardening: no implicit privilege, empty rejected, delegation bounded ------


def test_key_creation_without_role_or_scopes_is_rejected() -> None:
    """A key minted 'just with a name' must not silently become full-access."""
    _, master_key = _bootstrap()
    resp = client.post("/v1/orgs/keys", json={"name": "nameonly"}, headers=_auth(master_key))
    assert resp.status_code == 422
    assert "role" in resp.text and "scopes" in resp.text
    # And no key row was created for it.
    keys = client.get("/v1/orgs/keys", headers=_auth(master_key)).json()
    assert all(k["name"] != "nameonly" for k in keys)


def test_key_creation_with_empty_scopes_is_rejected() -> None:
    _, master_key = _bootstrap()
    resp = client.post(
        "/v1/orgs/keys", json={"name": "empty", "scopes": []}, headers=_auth(master_key)
    )
    assert resp.status_code == 422
    assert "empty" in resp.text.lower()


def test_no_implicit_wildcard_is_minted() -> None:
    """The only routes to a '*' key are an explicit role='owner' / scopes=['*'] — and the
    delegating caller must itself hold '*'. An admin key (no '*') cannot escalate."""
    _, master_key = _bootstrap()  # bootstrap key is role=admin -> [read,write,scan,admin]
    for body in ({"name": "sneak-owner", "role": "owner"}, {"name": "sneak-star", "scopes": ["*"]}):
        resp = client.post("/v1/orgs/keys", json=body, headers=_auth(master_key))
        assert resp.status_code == 403, resp.text
        assert "do not hold" in resp.text


def test_caller_cannot_grant_scope_it_does_not_hold() -> None:
    """Delegation boundary: an admin-only key can mint another admin key but not a
    write/read/scan key, since it does not itself hold those scopes."""
    _, master_key = _bootstrap()
    # An admin-only key: master holds 'admin', so it may delegate ['admin'].
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "admin-only", "scopes": ["admin"]},
        headers=_auth(master_key),
    )
    assert resp.status_code == 201, resp.text
    admin_only = resp.json()["api_key"]

    # It can reach the endpoint (has 'admin') and re-grant 'admin'...
    assert (
        client.post(
            "/v1/orgs/keys",
            json={"name": "child-admin", "scopes": ["admin"]},
            headers=_auth(admin_only),
        ).status_code
        == 201
    )
    # ...but cannot grant scopes it does not hold.
    escalation = client.post(
        "/v1/orgs/keys",
        json={"name": "child-write", "scopes": ["write", "admin"]},
        headers=_auth(admin_only),
    )
    assert escalation.status_code == 403
    assert "write" in escalation.text


def test_audit_events_require_admin_scope() -> None:
    _, master_key = _bootstrap()
    resp = client.post(
        "/v1/orgs/keys",
        json={"name": "viewer-key", "role": "viewer"},
        headers=_auth(master_key),
    )
    viewer_key = resp.json()["api_key"]
    assert client.get("/v1/audit-events", headers=_auth(viewer_key)).status_code == 403
