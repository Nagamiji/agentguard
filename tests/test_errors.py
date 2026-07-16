from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from keel.errors import http_exception_handler
from keel.middleware import ContextMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ContextMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    @app.get("/boom")
    def boom() -> None:
        raise StarletteHTTPException(status_code=418, detail="teapot")

    return app


def test_problem_details_shape() -> None:
    client = TestClient(_app())
    resp = client.get("/boom")
    assert resp.status_code == 418
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 418
    assert body["title"] == "teapot"
    assert body["instance"] == "/boom"
    assert "trace_id" in body
