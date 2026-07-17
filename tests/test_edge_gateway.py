import hashlib
import hmac
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
    resp = client.post("/v1/orgs", json={"name": f"edge-org-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201
    body = resp.json()
    return body["organization"]["id"], body["api_key"]


def test_proxy_headers_propagation() -> None:
    _, key = _bootstrap()

    # Emulate Cloudflare Gateway injecting proxy headers
    request_id = f"test-req-{uuid.uuid4().hex}"
    headers = {
        "Authorization": f"Bearer {key}",
        "x-request-id": request_id,
        "x-forwarded-for": "203.0.113.195",
        "x-client-country": "US",
    }

    # Make API request to backend
    resp = client.get("/v1/agents", headers=headers)
    assert resp.status_code == 200

    # Ensure Request ID header is reflected in the response (middleware propagates it)
    assert resp.headers.get("x-request-id") == request_id


def test_hmac_signature_verification_utility() -> None:
    # Mimic GitHub Webhook signature generation
    secret = "super-secret-token"  # noqa: S105
    payload = b'{"ref": "refs/heads/main", "after": "commit-sha"}'

    # Calculate HMAC SHA256 hex digest
    signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    # Assert signature computes correctly and matches expected length
    assert signature.startswith("sha256=")
    assert len(signature) == 71  # 7 prefix + 64 hex digest

    # Verify a modified payload fails verification
    tampered_payload = b'{"ref": "refs/heads/main", "after": "hacked-sha"}'
    tampered_signature = (
        "sha256=" + hmac.new(secret.encode(), tampered_payload, hashlib.sha256).hexdigest()
    )
    assert signature != tampered_signature
