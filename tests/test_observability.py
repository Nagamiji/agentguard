"""Observability Phase 1 — DB-free tests for exception logging and metric cardinality.

These need neither Postgres nor Redis: the exception handler and the metric-label helper
are exercised against a minimal app / pure function.
"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from keel.context import get_request_id
from keel.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from keel.metrics import metrics
from keel.middleware import ContextMiddleware, metric_path_label

# --- metric_path_label (pure) ------------------------------------------------------------


def test_single_path_param_is_templated() -> None:
    assert (
        metric_path_label("/v1/agents/abc123/gate", {"agent_id": "abc123"}, True)
        == "/v1/agents/{agent_id}/gate"
    )


def test_multiple_path_params_are_templated() -> None:
    got = metric_path_label(
        "/v1/agents/a-1/versions/v-2",
        {"agent_id": "a-1", "version_id": "v-2"},
        True,
    )
    assert got == "/v1/agents/{agent_id}/versions/{version_id}"


def test_static_matched_path_passes_through() -> None:
    assert metric_path_label("/healthz", {}, True) == "/healthz"


def test_unmatched_path_collapses_to_single_bucket() -> None:
    # A 404 scanner must not be able to invent unbounded label values.
    assert metric_path_label("/v1/does/not/exist/xyz", {}, False) == "unmatched"


def test_replacement_is_segment_wise_not_substring() -> None:
    # A param value equal to a whole segment is replaced; it must not be replaced where it
    # only appears as a substring of another segment.
    assert metric_path_label("/v1/v/items/v", {"p": "v"}, True) == "/v1/{p}/items/{p}"


# --- metric labelling end to end (real middleware, real registry, no DB) -----------------


def test_request_path_is_recorded_templated_not_raw() -> None:
    app = FastAPI()
    app.add_middleware(ContextMiddleware)

    @app.get("/obsvtest/{thing_id}/sub/{sub_id}")
    def _handler(thing_id: str, sub_id: str) -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/obsvtest/zzz-unique-9137/sub/qqq-unique-4471").status_code == 200

    rendered = metrics.render()
    assert 'path="/obsvtest/{thing_id}/sub/{sub_id}"' in rendered
    # The raw id values must never have become label values.
    assert "zzz-unique-9137" not in rendered
    assert "qqq-unique-4471" not in rendered


# --- unhandled exception logging ---------------------------------------------------------


def _app_that_booms() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ContextMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/boom")
    def _boom() -> dict[str, str]:
        raise RuntimeError("kaboom-internal-detail-must-not-leak")

    return app


def test_unhandled_exception_is_logged_with_context_and_not_leaked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = TestClient(_app_that_booms(), raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR, logger="keel.errors"):
        resp = client.get("/boom", headers={"X-Request-ID": "req-obsv-test-123"})

    # Client sees a generic 500 — never the internal message or a traceback.
    assert resp.status_code == 500
    assert "kaboom" not in resp.text
    assert resp.json()["error"]["request_id"] == "req-obsv-test-123"

    # Operators get a structured error log carrying the request context + the traceback.
    record = next(
        r
        for r in caplog.records
        if r.name == "keel.errors" and r.getMessage() == "unhandled_exception"
    )
    assert record.request_id == "req-obsv-test-123"  # type: ignore[attr-defined]
    assert record.method == "GET"  # type: ignore[attr-defined]
    assert record.path == "/boom"  # type: ignore[attr-defined]
    assert record.exc_info is not None


def test_request_id_is_none_outside_a_request() -> None:
    # Background jobs / CLI have no request context, so audit rows written there are NULL.
    assert get_request_id() is None
