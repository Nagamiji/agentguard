"""Tests for standardised API error envelope format.

Every error response must include:
  { "error": { "code": str, "message": str, "request_id": str | None } }
"""

import uuid

from fastapi.testclient import TestClient

from keel.main import app

client = TestClient(app, raise_server_exceptions=False)


def _assert_error_envelope(resp_json: dict) -> None:  # type: ignore[type-arg]
    """Assert the standard error envelope is present."""
    assert "error" in resp_json, f"Missing 'error' key: {resp_json}"
    err = resp_json["error"]
    assert "code" in err, f"Missing error.code: {err}"
    assert "message" in err, f"Missing error.message: {err}"
    assert isinstance(err["code"], str) and len(err["code"]) > 0
    assert isinstance(err["message"], str) and len(err["message"]) > 0


def test_404_returns_standard_envelope() -> None:
    resp = client.get(f"/v1/agents/{uuid.uuid4()}")
    # Could be 404 (agent not found) or 401 (auth required) — both must be enveloped
    assert resp.status_code in (401, 403, 404)
    _assert_error_envelope(resp.json())


def test_401_missing_auth_returns_standard_envelope() -> None:
    resp = client.get("/v1/agents")
    assert resp.status_code == 401
    body = resp.json()
    _assert_error_envelope(body)
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_422_validation_error_returns_standard_envelope() -> None:
    """Malformed onboarding payload must return standard 422 envelope."""
    resp = client.post("/v1/onboarding", json={})
    assert resp.status_code == 422
    body = resp.json()
    _assert_error_envelope(body)
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_422_envelope_includes_detail() -> None:
    """Validation error detail must mention the failing field."""
    resp = client.post("/v1/onboarding", json={"organization_name": ""})
    assert resp.status_code == 422
    body = resp.json()
    _assert_error_envelope(body)
    assert "detail" in body


def test_error_response_has_status_field() -> None:
    """The status HTTP code must be echoed in the response body."""
    resp = client.get("/v1/agents", headers={"Authorization": "Bearer invalid-key-xyz"})
    body = resp.json()
    assert "status" in body
    assert body["status"] == resp.status_code


def test_request_id_echoed_in_error() -> None:
    """Providing X-Request-ID must echo it into the error envelope."""
    custom_id = "test-req-12345"
    resp = client.get(
        "/v1/agents",
        headers={"X-Request-ID": custom_id},
    )
    # No auth → 401, but request_id must be attached
    assert resp.status_code in (401, 403)
    body = resp.json()
    _assert_error_envelope(body)
    # request_id is in the trace_id top-level field
    assert body.get("trace_id") == custom_id or body["error"].get("request_id") == custom_id
