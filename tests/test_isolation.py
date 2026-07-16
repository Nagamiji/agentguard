"""Integration tests: tenant isolation is enforced by Postgres RLS, not app code.

Requires a migrated database (`make up && make migrate`). Skipped locally when there is
no database; in CI (KEEL_REQUIRE_DB=1) a missing database is a failure, not a skip.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from keel.db import check_db
from keel.main import app

# CI sets KEEL_REQUIRE_DB=1: a missing database there means the service container
# broke, and skipping would turn the tenant-isolation guarantee into a silent pass.
_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")

client = TestClient(app)


def _bootstrap(label: str) -> tuple[str, str]:
    resp = client.post("/v1/orgs", json={"name": f"{label}-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["organization"]["id"], body["api_key"]


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_projects_are_isolated_between_tenants_by_rls() -> None:
    org_a, key_a = _bootstrap("org-a")
    org_b, key_b = _bootstrap("org-b")

    for key, name in ((key_a, "a-proj"), (key_b, "b-proj")):
        created = client.post("/v1/projects", json={"name": name}, headers=_auth(key))
        assert created.status_code == 201, created.text

    # The endpoint issues SELECT with NO organization filter — RLS must scope it.
    resp = client.get("/v1/projects", headers=_auth(key_a))
    assert resp.status_code == 200
    projects = resp.json()
    assert [p["name"] for p in projects] == ["a-proj"]
    assert {p["organization_id"] for p in projects} == {org_a}

    resp_b = client.get("/v1/projects", headers=_auth(key_b))
    assert [p["name"] for p in resp_b.json()] == ["b-proj"]
    assert {p["organization_id"] for p in resp_b.json()} == {org_b}


def test_missing_auth_is_rejected() -> None:
    assert client.get("/v1/projects").status_code == 401


def test_invalid_key_is_rejected() -> None:
    assert client.get("/v1/projects", headers=_auth("ag_not_a_real_key")).status_code == 401


def test_revoked_key_is_rejected() -> None:
    _, key = _bootstrap("org-revoke")
    issued = client.post("/v1/orgs/keys", json={"name": "temp"}, headers=_auth(key))
    assert issued.status_code == 201
    temp_key = issued.json()["api_key"]
    key_id = issued.json()["key"]["id"]

    assert client.get("/v1/projects", headers=_auth(temp_key)).status_code == 200
    assert client.delete(f"/v1/orgs/keys/{key_id}", headers=_auth(key)).status_code == 204
    assert client.get("/v1/projects", headers=_auth(temp_key)).status_code == 401


def test_cannot_revoke_another_orgs_key() -> None:
    _, key_a = _bootstrap("org-x")
    _, key_b = _bootstrap("org-y")
    issued = client.post("/v1/orgs/keys", json={"name": "victim"}, headers=_auth(key_b))
    victim_id = issued.json()["key"]["id"]

    resp = client.delete(f"/v1/orgs/keys/{victim_id}", headers=_auth(key_a))
    assert resp.status_code == 404  # not found *for this tenant*
