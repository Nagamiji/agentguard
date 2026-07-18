"""Tests for health, readiness, metrics, and version endpoints."""

import os

import pytest
from fastapi.testclient import TestClient

from keel.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    """Liveness endpoint must always succeed."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_health_alias_returns_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_version_endpoint() -> None:
    resp = client.get("/v1/version")
    assert resp.status_code == 200
    body = resp.json()
    assert "version" in body
    assert "environment" in body
    # Must be a non-empty string
    assert len(body["version"]) > 0
    assert len(body["environment"]) > 0


def test_readyz_without_db_returns_503_or_200() -> None:
    """Readiness either passes (if db available) or returns 503 — never 500."""
    resp = client.get("/readyz")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "status" in body
    assert "checks" in body
    assert "database" in body["checks"]
    assert "redis" in body["checks"]


def test_ready_alias() -> None:
    resp = client.get("/ready")
    assert resp.status_code in (200, 503)


def test_metrics_endpoint_returns_prometheus_text() -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    # Must include at least some metric lines
    assert "# HELP" in resp.text or "http_requests_total" in resp.text


_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"


@pytest.mark.skipif(not _require_db, reason="Postgres not available")
def test_readyz_with_db_returns_ready() -> None:
    """When Postgres IS available (integration test context), readyz must be 200."""
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] is True
