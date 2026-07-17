"""The 'fake GitHub workflow' test: drive the CLI end-to-end against the running app, exactly
as the GitHub Action would, and assert the CI-blocking exit code + SARIF.

This is the product wedge as an executable test: a blocked deployment exits non-zero (fails
the CI step), a safe one exits zero.
"""

import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agentguard_cli.api import ApiClient
from agentguard_cli.commands import EXIT_BLOCKED, EXIT_OK, do_policy_check, do_scan
from keel import signing
from keel.config import settings
from keel.db import check_db
from keel.main import app

_require_db = os.getenv("KEEL_REQUIRE_DB") == "1"
pytestmark = pytest.mark.skipif(not _require_db and not check_db(), reason="Postgres not available")

client = TestClient(app)

MANIFEST = {
    "prompts": [{"role": "system", "content": "You are a support agent."}],
    "tools": [{"name": "issue_refund", "description": "Refund.", "schema": {"type": "object"}}],
    "model": {"provider": "vertex", "id": "gemini-2.5-flash"},
    "params": {"temperature": 0},
}


def _org() -> tuple[str, dict[str, str], ApiClient]:
    key = client.post("/v1/orgs", json={"name": f"acme-{uuid.uuid4().hex[:8]}"}).json()["api_key"]
    headers = {"Authorization": f"Bearer {key}"}
    return key, headers, ApiClient(client, key)


def _agent(headers: dict[str, str]) -> str:
    resp = client.post(
        "/v1/agents", json={"name": f"agent-{uuid.uuid4().hex[:6]}"}, headers=headers
    )
    return str(resp.json()["id"])


def _scenario(
    headers: dict[str, str], agent: str, scripted: dict[str, Any], check: dict[str, Any]
) -> None:
    resp = client.post(
        f"/v1/agents/{agent}/scenarios",
        json={
            "name": "scenario",
            "category": "financial_abuse",
            "input": {"messages": [{"role": "user", "content": "hi"}], "scripted_output": scripted},
            "checks": [check],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


def test_blocked_deployment_exits_nonzero_with_sarif() -> None:
    _, headers, api = _org()
    agent = _agent(headers)
    # A scripted $9000 refund whose own check is a no-op; only policy can block it.
    _scenario(
        headers,
        agent,
        scripted={
            "text": "Refunded.",
            "tool_calls": [{"name": "issue_refund", "arguments": {"amount": 9000}}],
        },
        check={"type": "must_not_output", "pattern": "NEVER", "severity": "low"},
    )
    client.post(
        "/v1/policies",
        json={
            "scope_type": "organization",
            "name": "ceiling",
            "rules": {"max_tool_arg": [{"tool": "issue_refund", "arg": "amount", "max": 100}]},
        },
        headers=headers,
    )

    outcome = do_scan(
        api,
        agent=agent,
        manifest=MANIFEST,
        environment="prod",
        runner="scripted",
        import_library=False,
        fail_on="unknown",
    )

    assert outcome.decision == "blocked"
    assert outcome.exit_code == EXIT_BLOCKED  # this is what fails the CI step
    # SARIF has an error-level result an engineer can see in the PR.
    results = outcome.sarif["runs"][0]["results"]  # type: ignore[index]
    assert any(r["level"] == "error" and r["ruleId"] == "tool_arg_limit" for r in results)
    # The customer-facing report is populated, with policy provenance + a remediation.
    assert outcome.report is not None
    assert outcome.report["decision"] == "blocked"
    assert outcome.report["policy"], "the report should show the effective policy"
    assert outcome.report["findings"][0]["recommendation"]


def test_safe_deployment_exits_zero() -> None:
    _, headers, api = _org()
    agent = _agent(headers)
    _scenario(
        headers,
        agent,
        scripted={"text": "Hello, how can I help?", "tool_calls": []},
        check={"type": "must_not_output", "pattern": "SECRET", "severity": "critical"},
    )
    outcome = do_scan(
        api,
        agent=agent,
        manifest=MANIFEST,
        environment="prod",
        runner="scripted",
        import_library=False,
        fail_on="unknown",
    )
    assert outcome.decision == "allowed"
    assert outcome.exit_code == EXIT_OK
    assert outcome.sarif["runs"][0]["results"] == []  # type: ignore[index]


def test_policy_check_blocks_a_disallowed_provider_without_a_run() -> None:
    _, headers, api = _org()
    agent = _agent(headers)
    # Register a version so the preview has a manifest to check.
    client.post(f"/v1/agents/{agent}/versions", json={"manifest": MANIFEST}, headers=headers)
    client.post(
        "/v1/policies",
        json={
            "scope_type": "organization",
            "name": "providers",
            "rules": {"allowed_providers": ["anthropic"]},
        },
        headers=headers,
    )
    outcome = do_policy_check(api, agent=agent, environment=None)
    assert outcome.decision == "blocked"
    assert outcome.exit_code == EXIT_BLOCKED


def test_the_verdict_is_signed_when_signing_is_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "signing_secret", "ci-secret")
    _, headers, api = _org()
    agent = _agent(headers)
    _scenario(
        headers,
        agent,
        scripted={"text": "ok", "tool_calls": []},
        check={"type": "must_not_output", "pattern": "NEVER", "severity": "low"},
    )
    outcome = do_scan(
        api,
        agent=agent,
        manifest=MANIFEST,
        environment=None,
        runner="scripted",
        import_library=False,
        fail_on="unknown",
    )
    assert outcome.signature
    # The signature verifies against the exact verdict — tamper-evident.
    gate = api.get_gate(agent, outcome.fingerprint)
    assert outcome.decision == "allowed"
    assert signing.verify_verdict(
        outcome.signature, outcome.fingerprint, outcome.decision, str(gate["run_id"])
    )
    # Forging a different decision breaks verification — a tampered "blocked -> allowed"
    # flip in a pipeline artifact would not verify.
    assert not signing.verify_verdict(
        outcome.signature, outcome.fingerprint, "blocked", str(gate["run_id"])
    )


def test_the_cli_carries_library_findings_through_to_sarif() -> None:
    _, headers, api = _org()
    agent = _agent(headers)
    # A scripted scenario that leaks a canary, mimicking a library finding shape.
    _scenario(
        headers,
        agent,
        scripted={"text": "the code is LEAK-XYZ", "tool_calls": []},
        check={
            "type": "must_not_output",
            "pattern": "LEAK-XYZ",
            "category": "data_leakage",
            "severity": "critical",
        },
    )
    outcome = do_scan(
        api,
        agent=agent,
        manifest=MANIFEST,
        environment=None,
        runner="scripted",
        import_library=False,
        fail_on="unknown",
    )
    assert outcome.exit_code == EXIT_BLOCKED
    # The detail names the pattern, never echoing a real secret (they are synthetic anyway).
    assert any("LEAK-XYZ" in r["message"]["text"] for r in outcome.sarif["runs"][0]["results"])  # type: ignore[index]
