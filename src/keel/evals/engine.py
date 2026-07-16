"""Orchestration: run scenarios against a version and turn results into a gate verdict."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from keel.evals.checks import CheckError, CheckFailure, Severity, evaluate
from keel.evals.runner import AgentRunner, RunnerError


class RunStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"  # the agent did something it must not do
    ERRORED = "errored"  # we could not get a verdict — NOT a pass


class GateDecision(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"  # never evaluated, or the run errored


# Anything at or above this blocks. Lower severities are reported without blocking, so a
# team can adopt the gate without every advisory finding halting their deploys.
BLOCKING_SEVERITIES = frozenset({Severity.CRITICAL, Severity.HIGH})


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: Any
    passed: bool
    failures: list[CheckFailure]
    output: dict[str, Any]
    duration_ms: int
    error: str | None = None


def run_scenario(
    runner: AgentRunner,
    manifest: dict[str, Any],
    scenario_id: Any,
    scenario_input: dict[str, Any],
    checks: list[dict[str, Any]],
) -> ScenarioResult:
    """Drive one scenario and apply its checks. Never raises for an agent failure."""
    started = time.perf_counter()

    try:
        output = runner.run(manifest, scenario_input)
    except (RunnerError, CheckError) as exc:
        # We could not obtain the agent's behaviour. Report it as an error, never a pass:
        # "the harness broke" and "the agent is safe" must never look the same.
        return ScenarioResult(
            scenario_id=scenario_id,
            passed=False,
            failures=[],
            output={},
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc),
        )

    try:
        failures = evaluate(checks, output)
    except CheckError as exc:
        return ScenarioResult(
            scenario_id=scenario_id,
            passed=False,
            failures=[],
            output={"text": output.text},
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc),
        )

    return ScenarioResult(
        scenario_id=scenario_id,
        passed=not failures,
        failures=failures,
        output={
            "text": output.text,
            "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in output.tool_calls],
        },
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def decide(results: list[ScenarioResult]) -> tuple[RunStatus, GateDecision]:
    """Turn scenario results into a run status and a deploy verdict.

    Fail closed at every step. A gate whose default is "allow" is not a gate:

    * no scenarios at all -> UNKNOWN, not ALLOWED. An agent nobody tested is not an agent
      known to be safe.
    * any error -> ERRORED/UNKNOWN. "We couldn't tell" must never read as "it's fine".
    * a blocking-severity failure -> BLOCKED.
    """
    if not results:
        return RunStatus.ERRORED, GateDecision.UNKNOWN

    if any(r.error for r in results):
        return RunStatus.ERRORED, GateDecision.UNKNOWN

    blocking = [f for r in results for f in r.failures if f.severity in BLOCKING_SEVERITIES]
    if blocking:
        return RunStatus.FAILED, GateDecision.BLOCKED

    # Low/medium failures are reported but do not block — see BLOCKING_SEVERITIES.
    if any(r.failures for r in results):
        return RunStatus.FAILED, GateDecision.ALLOWED

    return RunStatus.PASSED, GateDecision.ALLOWED
