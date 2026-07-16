"""The provider contract, and the registry that resolves one by name."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from keel.evals.checks import ToolCall


class ProviderError(RuntimeError):
    """The model could not be reached or its reply could not be understood.

    Never the same as "the agent misbehaved". A provider error means we do not know what
    the agent would do, and the gate must report UNKNOWN rather than a pass.
    """


@dataclass(frozen=True)
class ProviderResponse:
    """One turn from the model."""

    # Defaults to empty: a turn that only calls a tool carries no prose, and that is the
    # most important turn there is.
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    # Recorded as evidence: which model actually answered. "gemini-2.5-flash" as requested
    # can resolve to a different served version, and a verdict about an unnamed model is
    # not reproducible.
    model_version: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""


class BaseModelProvider(Protocol):
    """Drives one turn of a conversation.

    Implementations MUST:
      * pass tool SCHEMAS to the model but never execute a tool — interception is the
        caller's job and the customer's tools are not ours to run (ADR 0008);
      * raise ProviderError rather than return an empty response on failure, so that
        "we could not tell" never renders as "nothing happened";
      * take credentials from the ambient environment, never from a manifest — a manifest
        is untrusted tenant input.
    """

    name: str

    def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        params: dict[str, Any],
    ) -> ProviderResponse: ...


def get_provider(name: str) -> BaseModelProvider:
    """Resolve a provider by name. Unknown names raise rather than fall back.

    A silent fallback to a stub would let a run report a verdict about a model that was
    never consulted.
    """
    if name == "vertex":
        from keel.evals.providers.vertex import VertexAIProvider

        return VertexAIProvider()
    raise ProviderError(f"unknown provider '{name}' (available: vertex)")
