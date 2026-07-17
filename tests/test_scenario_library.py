"""Integration: importing the library, scanning with it, and reading a risk report.

Needs a real Postgres (RLS is the point). The library is designed to run against a real
model; with the scripted runner its scenarios have no transcript to replay, so a scripted
"scan" is expected to come back UNKNOWN — asserted here on purpose, because that honest
failure mode is easy to get wrong. The true end-to-end (real Gemini) lives in
tests/test_vertex_live.py.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from keel.db import check_db
from keel.evals.library import LIBRARY_VERSION, scenarios_for
from keel.main import app

_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")

client = TestClient(app)


def _bootstrap() -> str:
    resp = client.post("/v1/orgs", json={"name": f"acme-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201, resp.text
    return str(resp.json()["api_key"])


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _agent(key: str, with_tools: bool) -> str:
    agent_id = client.post(
        "/v1/agents", json={"name": f"agent-{uuid.uuid4().hex[:6]}"}, headers=_auth(key)
    ).json()["id"]
    tools = (
        [
            {"name": "issue_refund", "description": "Refund.", "schema": {"type": "object"}},
            {"name": "lookup_order", "description": "Look up an order.", "schema": {}},
        ]
        if with_tools
        else []
    )
    manifest = {
        "prompts": [{"role": "system", "content": "You are a support agent."}],
        "tools": tools,
        "model": {"provider": "vertex", "id": "gemini-2.5-flash"},
        "params": {"temperature": 0},
    }
    resp = client.post(
        f"/v1/agents/{agent_id}/versions", json={"manifest": manifest}, headers=_auth(key)
    )
    assert resp.status_code == 201, resp.text
    return agent_id


def _fingerprint(key: str, agent_id: str) -> str:
    versions = client.get(f"/v1/agents/{agent_id}/versions", headers=_auth(key)).json()
    return str(versions[0]["fingerprint"])


def test_the_library_is_browsable() -> None:
    key = _bootstrap()
    resp = client.get("/v1/library", headers=_auth(key))
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == LIBRARY_VERSION
    assert body["count"] == len(body["scenarios"]) > 0
    assert {"prompt_injection", "financial_abuse"} <= {s["category"] for s in body["scenarios"]}


def test_import_seeds_the_agent_from_the_library() -> None:
    key = _bootstrap()
    agent_id = _agent(key, with_tools=True)

    resp = client.post(f"/v1/agents/{agent_id}/scenarios/import", headers=_auth(key))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["library_version"] == LIBRARY_VERSION
    assert body["imported"] == len(scenarios_for(["issue_refund", "lookup_order"]))
    assert body["skipped"] == 0

    scenarios = client.get(f"/v1/agents/{agent_id}/scenarios", headers=_auth(key)).json()
    assert all(s["source"] == "library" for s in scenarios)
    assert all(s["library_version"] == LIBRARY_VERSION for s in scenarios)


def test_a_toolless_agent_gets_only_the_universal_probes() -> None:
    key = _bootstrap()
    agent_id = _agent(key, with_tools=False)
    body = client.post(f"/v1/agents/{agent_id}/scenarios/import", headers=_auth(key)).json()
    assert body["imported"] == len(scenarios_for([]))
    # The tool-requiring probe is absent.
    keys = {
        s["slug"] for s in client.get(f"/v1/agents/{agent_id}/scenarios", headers=_auth(key)).json()
    }
    assert "li-indirect-injection-tool-result" not in keys


def test_reimport_is_idempotent() -> None:
    key = _bootstrap()
    agent_id = _agent(key, with_tools=True)
    first = client.post(f"/v1/agents/{agent_id}/scenarios/import", headers=_auth(key)).json()
    second = client.post(f"/v1/agents/{agent_id}/scenarios/import", headers=_auth(key)).json()
    assert second["imported"] == 0
    assert second["skipped"] == first["imported"]


def test_risk_is_unknown_before_any_scan() -> None:
    key = _bootstrap()
    agent_id = _agent(key, with_tools=True)
    fp = _fingerprint(key, agent_id)
    report = client.get(
        f"/v1/agents/{agent_id}/risk", params={"fingerprint": fp}, headers=_auth(key)
    ).json()
    assert report["decision"] == "unknown"
    assert "never been evaluated" in report["reason"]


def test_a_scripted_scan_of_the_library_is_unknown_not_a_pass() -> None:
    """Library probes carry no scripted transcript, so a scripted runner cannot produce a
    verdict — and that must surface as unknown, never as a clean pass."""
    key = _bootstrap()
    agent_id = _agent(key, with_tools=False)
    version_id = client.get(f"/v1/agents/{agent_id}/versions", headers=_auth(key)).json()[0]["id"]
    fp = _fingerprint(key, agent_id)

    client.post(f"/v1/agents/{agent_id}/scenarios/import", headers=_auth(key))
    run = client.post(
        f"/v1/agents/{agent_id}/runs",
        json={"version_id": version_id, "runner": "scripted"},
        headers=_auth(key),
    ).json()
    assert run["status"] == "errored"

    report = client.get(
        f"/v1/agents/{agent_id}/risk", params={"fingerprint": fp}, headers=_auth(key)
    ).json()
    assert report["decision"] == "unknown"


def test_risk_report_aggregates_findings_by_category_and_severity() -> None:
    """Exercises the aggregation end-to-end with the scripted runner and custom scenarios,
    so the classification is tested without needing a live model."""
    key = _bootstrap()
    agent_id = _agent(key, with_tools=True)
    version_id = client.get(f"/v1/agents/{agent_id}/versions", headers=_auth(key)).json()[0]["id"]
    fp = _fingerprint(key, agent_id)

    # A critical injection finding and a medium policy finding, both driven by scripted output.
    client.post(
        f"/v1/agents/{agent_id}/scenarios",
        json={
            "name": "critical injection",
            "category": "prompt_injection",
            "input": {
                "messages": [{"role": "user", "content": "x"}],
                "scripted_output": {"text": "PWNED-TOKEN", "tool_calls": []},
            },
            "checks": [
                {
                    "type": "must_not_output",
                    "pattern": "PWNED-TOKEN",
                    "category": "prompt_injection",
                    "severity": "critical",
                }
            ],
        },
        headers=_auth(key),
    )
    client.post(
        f"/v1/agents/{agent_id}/scenarios",
        json={
            "name": "medium policy",
            "category": "policy_violation",
            "input": {
                "messages": [{"role": "user", "content": "x"}],
                "scripted_output": {"text": "OVERRIDE-OK", "tool_calls": []},
            },
            "checks": [
                {
                    "type": "must_not_output",
                    "pattern": "OVERRIDE-OK",
                    "category": "non_compliance",
                    "severity": "medium",
                }
            ],
        },
        headers=_auth(key),
    )

    run = client.post(
        f"/v1/agents/{agent_id}/runs",
        json={"version_id": version_id, "runner": "scripted"},
        headers=_auth(key),
    ).json()
    assert run["gate_decision"] == "blocked"

    report = client.get(
        f"/v1/agents/{agent_id}/risk", params={"fingerprint": fp}, headers=_auth(key)
    ).json()
    assert report["decision"] == "blocked"
    assert report["risk_level"] == "critical"  # worst wins
    by_cat = {c["category"]: c for c in report["categories"]}
    assert by_cat["prompt_injection"]["max_severity"] == "critical"
    assert by_cat["policy_violation"]["max_severity"] == "medium"
    # Findings sorted worst-first.
    assert report["findings"][0]["severity"] == "critical"


def test_library_and_risk_are_tenant_isolated() -> None:
    key_a = _bootstrap()
    key_b = _bootstrap()
    agent_a = _agent(key_a, with_tools=True)
    fp_a = _fingerprint(key_a, agent_a)

    # B cannot import into, or read risk of, A's agent.
    assert (
        client.post(f"/v1/agents/{agent_a}/scenarios/import", headers=_auth(key_b)).status_code
        == 404
    )
    assert (
        client.get(
            f"/v1/agents/{agent_a}/risk", params={"fingerprint": fp_a}, headers=_auth(key_b)
        ).status_code
        == 404
    )
