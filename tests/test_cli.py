"""CLI unit tests: fingerprint, SARIF, exit-code logic, and API error handling. No DB."""

import json
from pathlib import Path
from typing import Any

import pytest

from agentguard_cli.api import ApiClient, ApiError
from agentguard_cli.commands import (
    EXIT_BLOCKED,
    EXIT_ERROR,
    EXIT_OK,
    EXIT_UNKNOWN,
    do_fingerprint,
    do_scan,
)
from agentguard_cli.sarif import build_sarif
from keel.fingerprint import compute_fingerprint

MANIFEST = {
    "prompts": [{"role": "system", "content": "You are a support agent."}],
    "tools": [{"name": "issue_refund", "schema": {}}],
    "model": {"provider": "vertex", "id": "gemini-2.5-flash"},
    "params": {"temperature": 0},
}


# --- fingerprint (local) ----------------------------------------------------------------


def test_fingerprint_command_matches_the_engine(tmp_path: Path) -> None:
    manifest_file = tmp_path / "m.json"
    manifest_file.write_text(json.dumps(MANIFEST))
    outcome = do_fingerprint(str(manifest_file))
    assert outcome.exit_code == EXIT_OK
    assert outcome.fingerprint == compute_fingerprint(MANIFEST)


def test_fingerprint_of_a_missing_file_fails_closed() -> None:
    outcome = do_fingerprint("/nope/does-not-exist.json")
    assert outcome.decision == "error"
    assert outcome.exit_code == EXIT_ERROR


# --- SARIF ------------------------------------------------------------------------------


def test_sarif_is_well_formed_and_maps_severity_to_level() -> None:
    findings = [
        {
            "check_type": "tool_arg_limit",
            "severity": "critical",
            "detail": "refund 9000 > 100",
            "category": "unsafe_tool_use",
        },
        {
            "check_type": "policy_x",
            "severity": "medium",
            "detail": "advisory",
            "category": "policy_violation",
        },
    ]
    sarif = build_sarif(
        agent="a",
        decision="blocked",
        fingerprint="fp",
        environment="prod",
        findings=findings,
        manifest_uri="agent.json",
        signature="sig",
    )
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "AgentGuard"
    assert len(run["results"]) == 2
    assert run["results"][0]["level"] == "error"  # critical -> error
    assert run["results"][1]["level"] == "warning"  # medium -> warning
    assert (
        run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        == "agent.json"
    )
    # A rule is registered per unique check_type.
    assert {r["id"] for r in run["tool"]["driver"]["rules"]} == {"tool_arg_limit", "policy_x"}


# --- exit-code logic (the CI contract) --------------------------------------------------


class FakeApi:
    """A stand-in ApiClient: canned responses or a raised ApiError."""

    def __init__(
        self,
        *,
        gate: dict[str, Any] | None = None,
        risk: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self._gate = gate or {}
        self._risk = risk or {}
        self._error = error

    def create_version(self, agent: str, manifest: dict[str, Any]) -> dict[str, Any]:
        if self._error:
            raise ApiError(self._error)
        return {"id": "v1", "fingerprint": "fp"}

    def import_library(self, agent: str) -> dict[str, Any]:
        return {}

    def create_run(
        self, agent: str, version_id: str, runner: str, environment: str | None
    ) -> dict[str, Any]:
        return {}

    def get_gate(self, agent: str, fingerprint: str) -> dict[str, Any]:
        return self._gate

    def get_risk(self, agent: str, fingerprint: str) -> dict[str, Any]:
        return self._risk

    def get_agent(self, agent: str) -> dict[str, Any]:
        return {"name": "test-agent"}

    def get_policy(self, agent: str, environment: str | None) -> dict[str, Any]:
        return {"effective": {}, "deferred_runtime": []}


def _scan(**api_kwargs: Any) -> Any:
    api = FakeApi(**api_kwargs)
    return do_scan(
        api,  # type: ignore[arg-type]
        agent="a",
        manifest=MANIFEST,
        environment=None,
        runner="scripted",
        import_library=False,
        fail_on="unknown",
    )


def test_blocked_verdict_exits_blocked() -> None:
    out = _scan(
        gate={
            "decision": "blocked",
            "fingerprint": "fp",
            "failures": [{"check_type": "tool_arg_limit", "severity": "critical", "detail": "d"}],
        },
        risk={"risk_level": "critical"},
    )
    assert out.decision == "blocked"
    assert out.exit_code == EXIT_BLOCKED
    assert out.sarif is not None and out.sarif["runs"][0]["results"]


def test_allowed_verdict_exits_ok() -> None:
    out = _scan(
        gate={"decision": "allowed", "fingerprint": "fp", "failures": []},
        risk={"risk_level": "none"},
    )
    assert out.exit_code == EXIT_OK


def test_unknown_verdict_fails_closed_by_default() -> None:
    out = _scan(gate={"decision": "unknown", "fingerprint": "fp", "failures": []}, risk={})
    assert out.exit_code == EXIT_UNKNOWN


def test_an_api_error_fails_closed_never_a_pass() -> None:
    out = _scan(error="connection refused")
    assert out.decision == "error"
    assert out.exit_code == EXIT_ERROR
    assert "connection refused" in out.reason


# --- ApiClient error handling -----------------------------------------------------------


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> Any:
        return self._payload


class _Http:
    def __init__(self, resp: Any = None, raise_exc: bool = False) -> None:
        self._resp = resp
        self._raise = raise_exc

    def get(self, url: str, **kwargs: Any) -> Any:
        if self._raise:
            raise RuntimeError("network down")
        return self._resp

    post = get


def test_apiclient_raises_on_http_error() -> None:
    client = ApiClient(_Http(_Resp(404, {"title": "not found"})), "key")
    with pytest.raises(ApiError) as exc:
        client.get_gate("a", "fp")
    assert exc.value.status_code == 404


def test_apiclient_raises_on_transport_error() -> None:
    client = ApiClient(_Http(raise_exc=True), "key")
    with pytest.raises(ApiError, match="could not reach"):
        client.get_gate("a", "fp")


# --- main() entry point -----------------------------------------------------------------


def test_main_fingerprint_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from agentguard_cli.main import main

    manifest_file = tmp_path / "m.json"
    manifest_file.write_text(json.dumps(MANIFEST))
    assert main(["fingerprint", str(manifest_file)]) == EXIT_OK
    assert compute_fingerprint(MANIFEST) in capsys.readouterr().out


def test_main_scan_fails_closed_when_the_server_is_unreachable(tmp_path: Path) -> None:
    """The end-to-end fail-closed contract: no server -> non-zero exit, never 0."""
    from agentguard_cli.main import main

    manifest_file = tmp_path / "m.json"
    manifest_file.write_text(json.dumps(MANIFEST))
    # Port 1 refuses immediately.
    code = main(
        [
            "scan",
            "--agent",
            "x",
            "--manifest",
            str(manifest_file),
            "--api-url",
            "http://127.0.0.1:1",
            "--api-key",
            "k",
        ]
    )
    assert code == EXIT_ERROR
