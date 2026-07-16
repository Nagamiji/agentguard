"""Runners: produce an AgentOutput from a manifest + a scenario input.

A runner drives the agent's decision-making. It NEVER executes the agent's tools — when the
agent asks for one, the scenario's canned result is returned instead (ADR 0008). The tool
schemas are passed to the model because the agent needs to know what it *could* do; the
implementations are the customer's and stay on the customer's side.
"""

from __future__ import annotations

from typing import Any, Protocol

from keel.evals.checks import AgentOutput, ToolCall


class RunnerError(RuntimeError):
    """The agent could not be driven to a verdict. Distinct from the agent FAILING.

    The difference matters at the gate: a failed check means "this agent is unsafe" and must
    block. A runner error means "we don't know", which must NOT be reported as a pass.
    """


class AgentRunner(Protocol):
    """Drives one scenario against one agent version."""

    def run(self, manifest: dict[str, Any], scenario_input: dict[str, Any]) -> AgentOutput: ...


class ScriptedRunner:
    """Replays a transcript recorded on the scenario. Deterministic; no model, no network.

    This is a TEST DOUBLE and cannot validate itself: it proves the detection layer catches
    dangerous behaviour once observed, not that a live model would produce that behaviour.
    Real execution is EVAL-02 (LiteLLMRunner). Nothing here should be read as evidence about
    a real model.

    It is not only scaffolding, though — a recorded transcript is a real regression fixture.
    Replaying the exact transcript that once broke you, on every deploy, forever, is
    precisely what a gate is for, and it is free of model non-determinism.
    """

    def run(self, manifest: dict[str, Any], scenario_input: dict[str, Any]) -> AgentOutput:
        transcript = scenario_input.get("scripted_output")
        if not isinstance(transcript, dict):
            raise RunnerError(
                "ScriptedRunner needs a 'scripted_output' object on the scenario input"
            )

        text = transcript.get("text", "")
        if not isinstance(text, str):
            raise RunnerError("'scripted_output.text' must be a string")

        raw_calls = transcript.get("tool_calls", [])
        if not isinstance(raw_calls, list):
            raise RunnerError("'scripted_output.tool_calls' must be a list")

        calls: list[ToolCall] = []
        for raw in raw_calls:
            if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
                raise RunnerError("each tool call needs a string 'name'")
            arguments = raw.get("arguments", {})
            if not isinstance(arguments, dict):
                raise RunnerError(f"tool call '{raw['name']}' needs an object 'arguments'")
            calls.append(ToolCall(name=raw["name"], arguments=arguments))

        return AgentOutput(text=text, tool_calls=tuple(calls))


def get_runner(name: str) -> AgentRunner:
    """Resolve a runner by name.

    Unknown names raise rather than defaulting to `scripted`: a silent fallback to the test
    double would let a run report a verdict about a model nobody consulted.
    """
    if name == "scripted":
        return ScriptedRunner()
    if name == "vertex":
        # Imported lazily so that the scripted path — and every unit test — needs neither
        # google-auth nor network access.
        from keel.evals.live import LiveAgentRunner
        from keel.evals.providers import get_provider

        return LiveAgentRunner(get_provider("vertex"))
    raise RunnerError(f"unknown runner '{name}' (available: scripted, vertex)")
