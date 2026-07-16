"""Model providers: turn a manifest + conversation into a model's next move.

A provider is the only part of the system that talks to an LLM. Everything above it —
interception, checks, the gate — is provider-agnostic on purpose: customers run on
Anthropic, Vertex, Bedrock and OpenAI, and a reliability gate that only works on one of
them is not a gate they can adopt.
"""

from keel.evals.providers.base import (
    BaseModelProvider,
    ProviderError,
    ProviderResponse,
    get_provider,
)

__all__ = ["BaseModelProvider", "ProviderError", "ProviderResponse", "get_provider"]
