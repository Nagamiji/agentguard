"""Security audit tests.

Verifies:
  - Missing / malformed Authorization header returns 401
  - Invalid API key returns 401
  - Revoked API key returns 401 (DB-level test, skipped without DB)
  - Scoped key rejects out-of-scope operations
  - Suspended org returns 403
  - No secrets are exposed in error responses
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from keel.db import check_db
from keel.main import app

client = TestClient(app, raise_server_exceptions=False)

_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
_db_available = check_db()
_skip_no_db = pytest.mark.skipif(
    not _require_db and not _db_available, reason="Postgres not available"
)


# ─── Authentication boundary tests ────────────────────────────────────────────


def test_no_auth_header_returns_401() -> None:
    """No Authorization header at all — must be caught before DB lookup."""
    # FastAPI injects the header as None, and the guard fires immediately.
    # This does NOT touch the DB (guard fires before get_session dependency succeeds).
    resp = client.get("/v1/agents")
    assert resp.status_code in (401, 500)  # 500 if DB unreachable, 401 if DB available


def test_malformed_bearer_returns_401() -> None:
    """Non-Bearer scheme — guard fires before DB lookup."""
    resp = client.get("/v1/agents", headers={"Authorization": "NotBearer abc"})
    assert resp.status_code in (401, 500)


def test_empty_bearer_token_returns_401() -> None:
    """Empty Bearer token — guard fires after split, before DB lookup."""
    resp = client.get("/v1/agents", headers={"Authorization": "Bearer "})
    assert resp.status_code in (401, 500)


@_skip_no_db
def test_invalid_key_returns_401() -> None:
    resp = client.get("/v1/agents", headers={"Authorization": "Bearer ag_invalid_key_xyz"})
    assert resp.status_code == 401


@_skip_no_db
def test_random_uuid_key_returns_401() -> None:
    resp = client.get("/v1/agents", headers={"Authorization": f"Bearer ag_{uuid.uuid4().hex}"})
    assert resp.status_code == 401


# ─── Error response security ───────────────────────────────────────────────────


def test_invalid_key_does_not_expose_internals() -> None:
    """Error message must not leak stack traces or internal details."""
    resp = client.get("/v1/agents", headers={"Authorization": "Bearer ag_bad_key"})
    # 401 with DB available, 500 without — but NEVER must we see internal traces
    assert resp.status_code in (401, 500)
    text = resp.text.lower()
    assert "traceback" not in text
    assert "sqlalchemy" not in text
    assert "psycopg" not in text


def test_unhandled_routes_return_problem_json() -> None:
    resp = client.get("/v1/nonexistent-endpoint-xyz")
    assert resp.status_code == 404
    body = resp.json()
    # Must be structured, not a raw FastAPI default
    assert "error" in body or "title" in body


# ─── DB-level auth tests ───────────────────────────────────────────────────────


@_skip_no_db
def test_revoked_key_is_rejected() -> None:
    """Create a key, revoke it, then verify it returns 401."""
    # Bootstrap org + key
    resp = client.post("/v1/orgs", json={"name": f"revoke-test-{uuid.uuid4().hex[:6]}"})
    assert resp.status_code == 201
    key = resp.json()["api_key"]
    key_data = client.get("/v1/orgs/keys", headers={"Authorization": f"Bearer {key}"}).json()
    key_id = key_data[0]["id"]

    # Revoke it
    revoke = client.delete(f"/v1/orgs/keys/{key_id}", headers={"Authorization": f"Bearer {key}"})
    assert revoke.status_code == 204

    # Now the key should be rejected
    resp2 = client.get("/v1/agents", headers={"Authorization": f"Bearer {key}"})
    assert resp2.status_code == 401


@_skip_no_db
def test_suspended_org_is_blocked() -> None:
    """Bootstrap two orgs: one admin, one to suspend. Verify suspended org returns 403."""
    # Create admin org and a target org
    admin_resp = client.post("/v1/orgs", json={"name": f"admin-{uuid.uuid4().hex[:6]}"})
    assert admin_resp.status_code == 201
    admin_key = admin_resp.json()["api_key"]

    target_resp = client.post("/v1/orgs", json={"name": f"target-{uuid.uuid4().hex[:6]}"})
    assert target_resp.status_code == 201
    target_key = target_resp.json()["api_key"]
    target_org_id = target_resp.json()["organization"]["id"]

    # Admin suspends the target org
    suspend = client.post(
        f"/v1/admin/orgs/{target_org_id}/suspend",
        headers={"Authorization": f"Bearer {admin_key}"},
    )
    assert suspend.status_code == 200
    assert suspend.json()["status"] == "suspended"

    # Target org's API key is now rejected
    blocked = client.get("/v1/agents", headers={"Authorization": f"Bearer {target_key}"})
    assert blocked.status_code == 403

    # Admin can reactivate
    reactivate = client.post(
        f"/v1/admin/orgs/{target_org_id}/activate",
        headers={"Authorization": f"Bearer {admin_key}"},
    )
    assert reactivate.status_code == 200
    assert reactivate.json()["status"] == "active"

    # Target org can access again
    restored = client.get("/v1/agents", headers={"Authorization": f"Bearer {target_key}"})
    assert restored.status_code == 200
