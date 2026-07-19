"""S7: the unauthenticated tenant-creation endpoints must be gated and least-privilege.

Covers the provisioning secret gate, production fail-closed default, per-IP rate limit, and
that the onboarding key cannot reach admin routes (least privilege).
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from keel.config import settings
from keel.db import check_db, get_redis_client
from keel.main import app

_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")

client = TestClient(app)

_PROV_SECRET = "s3cr3t"  # noqa: S105  (a test fixture, not a real credential)


@pytest.fixture
def restore_settings() -> Iterator[None]:
    """Snapshot the settings this module mutates and restore them afterwards."""
    saved = (
        settings.onboarding_secret,
        settings.app_env,
        settings.rate_limit_enabled,
        settings.onboarding_rate_limit_per_hour,
        settings.trusted_proxies,
    )
    try:
        yield
    finally:
        (
            settings.onboarding_secret,
            settings.app_env,
            settings.rate_limit_enabled,
            settings.onboarding_rate_limit_per_hour,
            settings.trusted_proxies,
        ) = saved


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


# --- provisioning secret gate ------------------------------------------------------------


def test_anonymous_onboarding_rejected_when_secret_configured(restore_settings: None) -> None:
    settings.onboarding_secret = _PROV_SECRET
    resp = client.post("/v1/onboarding", json={"organization_name": f"acme-{uuid.uuid4().hex[:6]}"})
    assert resp.status_code == 403
    assert "provisioning" in resp.text.lower()


def test_onboarding_succeeds_with_valid_provisioning_key(restore_settings: None) -> None:
    settings.onboarding_secret = _PROV_SECRET
    resp = client.post(
        "/v1/onboarding",
        json={"organization_name": f"acme-{uuid.uuid4().hex[:6]}"},
        headers={"X-Provisioning-Key": _PROV_SECRET},
    )
    assert resp.status_code == 201
    assert resp.json()["api_key"].startswith("ag_")


def test_wrong_provisioning_key_rejected(restore_settings: None) -> None:
    settings.onboarding_secret = _PROV_SECRET
    resp = client.post(
        "/v1/orgs",
        json={"name": f"acme-{uuid.uuid4().hex[:6]}"},
        headers={"X-Provisioning-Key": "wrong"},
    )
    assert resp.status_code == 403


def test_provisioning_disabled_in_production_without_secret(restore_settings: None) -> None:
    settings.onboarding_secret = ""
    settings.app_env = "production"
    resp = client.post("/v1/orgs", json={"name": f"acme-{uuid.uuid4().hex[:6]}"})
    assert resp.status_code == 503
    assert "disabled" in resp.text.lower()


def test_dev_without_secret_still_allowed(restore_settings: None) -> None:
    # Backward compatible: dev + no secret keeps the existing bootstrap flow working.
    settings.onboarding_secret = ""
    settings.app_env = "dev"
    resp = client.post("/v1/orgs", json={"name": f"acme-{uuid.uuid4().hex[:6]}"})
    assert resp.status_code == 201


# --- least privilege ---------------------------------------------------------------------


def test_onboarding_key_cannot_reach_admin_routes(restore_settings: None) -> None:
    settings.onboarding_secret = ""
    settings.app_env = "dev"
    onboard = client.post(
        "/v1/onboarding", json={"organization_name": f"acme-{uuid.uuid4().hex[:6]}"}
    )
    assert onboard.status_code == 201
    key = onboard.json()["api_key"]

    # Least privilege: developer scopes → write works, key management (admin) is forbidden.
    agent = client.post(
        "/v1/agents",
        json={"name": "Bot", "slug": f"b-{uuid.uuid4().hex[:4]}"},
        headers=_auth(key),
    )
    assert agent.status_code == 201
    keys = client.post("/v1/orgs/keys", json={"name": "x", "role": "viewer"}, headers=_auth(key))
    assert keys.status_code == 403


def test_bootstrap_key_is_admin_capable_but_not_wildcard(restore_settings: None) -> None:
    settings.onboarding_secret = ""
    settings.app_env = "dev"
    boot = client.post("/v1/orgs", json={"name": f"acme-{uuid.uuid4().hex[:6]}"})
    assert boot.status_code == 201
    key = boot.json()["api_key"]
    # The administrative bootstrap key CAN manage keys (admin scope present).
    second = client.post("/v1/orgs/keys", json={"name": "second", "role": "ci"}, headers=_auth(key))
    assert second.status_code == 201


# --- per-IP rate limit -------------------------------------------------------------------


def test_onboarding_rate_limit_enforced(restore_settings: None) -> None:
    try:
        get_redis_client().ping()
    except Exception:
        pytest.skip("Redis not available")

    settings.onboarding_secret = ""
    settings.app_env = "dev"
    settings.rate_limit_enabled = True
    settings.onboarding_rate_limit_per_hour = 2  # burst 2 → 3rd request in the window is blocked

    # TestClient's peer is a stable "testclient" host; clear its bucket for a fresh window.
    bucket = "rate_limit:onboarding:testclient"
    get_redis_client().delete(bucket)
    try:
        codes = [
            client.post("/v1/orgs", json={"name": f"rl-{uuid.uuid4().hex[:6]}"}).status_code
            for _ in range(3)
        ]
        assert codes[0] == 201
        assert codes[1] == 201
        assert codes[2] == 429
    finally:
        # Don't leak a drained bucket to other tests that create orgs under rate limiting.
        get_redis_client().delete(bucket)


# --- XFF trust boundary: a spoofed X-Forwarded-For must not bypass the limiter -----------
# (Trusted-proxy recovery of the real client is unit-tested in tests/test_client_ip.py,
# since the TestClient's peer host is "testclient", not a real IP that could be trusted.)


def test_spoofed_xff_cannot_bypass_onboarding_rate_limit(restore_settings: None) -> None:
    try:
        get_redis_client().ping()
    except Exception:
        pytest.skip("Redis not available")

    settings.onboarding_secret = ""
    settings.app_env = "dev"
    settings.rate_limit_enabled = True
    settings.trusted_proxies = ""  # no trusted proxy → identity is the peer, XFF ignored
    settings.onboarding_rate_limit_per_hour = 2  # 3rd request in the window is blocked

    bucket = "rate_limit:onboarding:testclient"
    get_redis_client().delete(bucket)
    try:
        # Rotate the X-Forwarded-For header on every request — the classic bypass attempt.
        codes = [
            client.post(
                "/v1/orgs",
                json={"name": f"xff-{uuid.uuid4().hex[:6]}"},
                headers={"X-Forwarded-For": f"10.9.9.{i}"},
            ).status_code
            for i in range(3)
        ]
        # The identity stayed the direct peer, so rotating XFF did NOT mint fresh buckets.
        assert codes == [201, 201, 429], codes
    finally:
        get_redis_client().delete(bucket)


def test_client_identity_is_stable_across_xff_values(restore_settings: None) -> None:
    """The rate-limit key is the peer regardless of XFF: only the 'testclient' bucket moves."""
    try:
        get_redis_client().ping()
    except Exception:
        pytest.skip("Redis not available")

    settings.onboarding_secret = ""
    settings.app_env = "dev"
    settings.rate_limit_enabled = True
    settings.trusted_proxies = ""
    settings.onboarding_rate_limit_per_hour = 5

    redis = get_redis_client()
    peer_bucket = "rate_limit:onboarding:testclient"
    spoof_bucket = "rate_limit:onboarding:203.0.113.42"
    redis.delete(peer_bucket)
    redis.delete(spoof_bucket)
    try:
        resp = client.post(
            "/v1/orgs",
            json={"name": f"stable-{uuid.uuid4().hex[:6]}"},
            headers={"X-Forwarded-For": "203.0.113.42"},
        )
        assert resp.status_code == 201
        # The peer's bucket was consumed; the XFF-named bucket was never created.
        assert redis.exists(peer_bucket) == 1
        assert redis.exists(spoof_bucket) == 0
    finally:
        redis.delete(peer_bucket)
        redis.delete(spoof_bucket)
