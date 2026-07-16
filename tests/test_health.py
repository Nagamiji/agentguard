from fastapi.testclient import TestClient

from keel.main import app

client = TestClient(app)


def test_healthz_ok() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_request_id_header_present() -> None:
    resp = client.get("/healthz")
    header_keys = {k.lower() for k in resp.headers}
    assert "x-request-id" in header_keys
