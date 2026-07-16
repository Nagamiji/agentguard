"""LiveAgentRunner: drive a real model, intercept every tool call, record the evidence.

The interception is the safety property, and it is structural rather than a policy someone
could forget: this module has no way to execute a tool. It holds no client, no callable, no
registry of implementations — only the customer's canned results from the scenario. There
is no code path from "the model asked for issue_refund" to anything running.

That is deliberate (ADR 0008). A guard that *decides* not to call a tool can be bypassed by
a bug; a guard that *cannot* call one cannot.
"""

from __future__ import annotations

import json
from typing import Any

from keel.config import settings
from keel.evals.checks import AgentOutput, ToolCall
from keel.evals.providers.base import BaseModelProvider, ProviderError
from keel.evals.runner import RunnerError


def _canned_result(scenario_input: dict[str, Any], call: ToolCall) -> Any:
    """What the scenario says this tool returns. Never what the tool would really return."""
    results = scenario_input.get("tool_results")
    if isinstance(results, dict) and call.name in results:
        return results[call.name]
    # No canned result: say so honestly in-band rather than inventing plausible data, which
    # would be us hallucinating on the agent's behalf and testing a fiction we authored.
    return {
        "error": "no simulated result configured for this tool",
        "note": "AgentGuard evaluation: tools are never really executed",
    }


class LiveAgentRunner:
    """Runs a scenario against a real model via a provider.

    Multi-turn: the model may call a tool, receive the scenario's canned result, and carry
    on. Every attempted call across every turn is collected, because the attempt is the
    signal — an agent that tries to refund $9,000 has already failed, whether or not a later
    turn would have "corrected" itself.
    """

    def __init__(self, provider: BaseModelProvider, max_turns: int | None = None) -> None:
        self.provider = provider
        self.max_turns = max_turns or settings.eval_max_turns
        self.trace: list[dict[str, Any]] = []

    def run(self, manifest: dict[str, Any], scenario_input: dict[str, Any]) -> AgentOutput:
        system = self._system_prompt(manifest)
        tools = manifest.get("tools") or []
        if not isinstance(tools, list):
            raise RunnerError("manifest 'tools' must be a list")
        params = manifest.get("params") or {}
        if not isinstance(params, dict):
            raise RunnerError("manifest 'params' must be an object")

        messages = self._initial_messages(manifest, scenario_input)
        if not messages:
            raise RunnerError("scenario input needs a non-empty 'messages' list")

        self.trace = []
        all_calls: list[ToolCall] = []
        final_text = ""

        for turn in range(self.max_turns):
            try:
                response = self.provider.generate(
                    system=system, messages=messages, tools=tools, params=params
                )
            except ProviderError as exc:
                # Surface as a runner error: the gate reports UNKNOWN, never a pass.
                raise RunnerError(str(exc)) from exc

            self.trace.append(
                {
                    "turn": turn,
                    "model_version": response.model_version,
                    "finish_reason": response.finish_reason,
                    "text": response.text,
                    "tool_calls": [
                        {"name": c.name, "arguments": c.arguments} for c in response.tool_calls
                    ],
                    "usage": response.usage,
                }
            )

            if response.text:
                final_text = response.text
            all_calls.extend(response.tool_calls)

            if not response.tool_calls:
                break

            # The model's turn, verbatim, so the conversation stays coherent.
            messages.append(
                {
                    "role": "model",
                    "parts": [
                        {"functionCall": {"name": c.name, "args": c.arguments}}
                        for c in response.tool_calls
                    ],
                }
            )
            # INTERCEPTED. The tool is not called; the scenario's canned result is returned.
            messages.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": c.name,
                                "response": {"result": _canned_result(scenario_input, c)},
                            }
                        }
                        for c in response.tool_calls
                    ],
                }
            )
        else:
            # Loop exhausted: the agent never settled. Report it rather than judging a
            # truncated transcript as if it were the agent's final answer.
            raise RunnerError(
                f"agent did not finish within {self.max_turns} turns "
                f"({len(all_calls)} tool calls attempted)"
            )

        return AgentOutput(text=final_text, tool_calls=tuple(all_calls))

    @staticmethod
    def _system_prompt(manifest: dict[str, Any]) -> str:
        parts = []
        for prompt in manifest.get("prompts") or []:
            if isinstance(prompt, dict) and prompt.get("role") == "system":
                content = prompt.get("content")
                if isinstance(content, str):
                    parts.append(content)
        return "\n\n".join(parts)

    @staticmethod
    def _initial_messages(
        manifest: dict[str, Any], scenario_input: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Build the conversation: the manifest's non-system prompts, then the scenario's."""
        messages: list[dict[str, Any]] = []

        def add(role: str, content: str) -> None:
            # Gemini has no 'assistant' role; its model turns are 'model'. Anything that is
            # not the model speaking is a 'user' turn.
            messages.append(
                {
                    "role": "model" if role in ("model", "assistant") else "user",
                    "parts": [{"text": content}],
                }
            )

        for prompt in manifest.get("prompts") or []:
            if isinstance(prompt, dict) and prompt.get("role") != "system":
                content = prompt.get("content")
                if isinstance(content, str):
                    add(str(prompt.get("role", "user")), content)

        for message in scenario_input.get("messages") or []:
            if not isinstance(message, dict):
                raise RunnerError("each scenario message must be an object")
            content = message.get("content")
            if not isinstance(content, str):
                raise RunnerError("each scenario message needs string 'content'")
            add(str(message.get("role", "user")), content)

        return messages

    def evidence(self) -> dict[str, Any]:
        """The reproducible record of what happened. Attached to the result."""
        return {
            "provider": getattr(self.provider, "name", "unknown"),
            "model": getattr(self.provider, "model", ""),
            "turns": len(self.trace),
            "trace": self.trace,
        }


def summarise_usage(trace: list[dict[str, Any]]) -> dict[str, int]:
    """Total tokens across a run. Cost control starts with knowing what a run costs."""
    totals = {"prompt_tokens": 0, "candidates_tokens": 0, "total_tokens": 0}
    for step in trace:
        usage = step.get("usage") or {}
        totals["prompt_tokens"] += int(usage.get("promptTokenCount", 0) or 0)
        totals["candidates_tokens"] += int(usage.get("candidatesTokenCount", 0) or 0)
        totals["total_tokens"] += int(usage.get("totalTokenCount", 0) or 0)
    return totals


def _json_safe(value: Any) -> Any:
    """Evidence goes into JSONB; anything unserialisable becomes a string rather than a 500."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
