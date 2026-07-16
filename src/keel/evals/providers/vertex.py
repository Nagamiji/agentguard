"""Google Vertex AI (Gemini) provider.

Talks to the Vertex REST `generateContent` endpoint directly over httpx, authenticated with
Application Default Credentials.

Why REST rather than the google-cloud-aiplatform SDK: the SDK is a large dependency with a
fast-moving surface, and all we need is one endpoint whose request/response shape is stable
and verified. Fewer moving parts in the component that decides whether a deploy is blocked.
ADC means no credential ever appears in our code, our config, or a manifest.
"""

from __future__ import annotations

from typing import Any

import httpx

from keel.config import settings
from keel.evals.checks import ToolCall
from keel.evals.providers.base import ProviderError, ProviderResponse

_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class VertexAIProvider:
    """Gemini via Vertex AI."""

    name = "vertex"

    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.project = project or settings.vertex_project
        self.location = location or settings.vertex_location
        self.model = model or settings.vertex_model
        self.timeout = timeout or settings.eval_timeout_seconds
        self._credentials: Any = None

    # --- auth ---------------------------------------------------------------------------

    def _token(self) -> str:
        """Fetch (and refresh) an ADC access token.

        Deliberately no fallback to an API key in config: ADC keeps credentials out of the
        process's own settings, which is the property that makes a leaked config harmless.
        """
        try:
            import google.auth
            from google.auth.transport.requests import Request as GoogleRequest
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise ProviderError("google-auth is not installed") from exc

        try:
            if self._credentials is None:
                self._credentials, discovered = google.auth.default(scopes=[_SCOPE])
                if not self.project:
                    self.project = discovered or ""
            if not self._credentials.valid:
                self._credentials.refresh(GoogleRequest())
        except Exception as exc:
            raise ProviderError(
                "Vertex authentication failed. Set GOOGLE_APPLICATION_CREDENTIALS or run "
                f"`gcloud auth application-default login`. ({exc})"
            ) from exc

        token = getattr(self._credentials, "token", None)
        if not token:
            raise ProviderError("Vertex authentication returned no access token")
        return str(token)

    # --- request/response translation ---------------------------------------------------

    @staticmethod
    def _to_gemini_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map our manifest tool schemas onto Gemini functionDeclarations."""
        declarations = []
        for tool in tools:
            name = tool.get("name")
            if not isinstance(name, str):
                raise ProviderError("each tool in the manifest needs a string 'name'")
            declaration: dict[str, Any] = {"name": name}
            if isinstance(tool.get("description"), str):
                declaration["description"] = tool["description"]
            schema = tool.get("schema") or tool.get("parameters")
            # Gemini rejects an empty parameters object, so omit it entirely for a
            # no-argument tool rather than sending `{}`.
            if isinstance(schema, dict) and schema:
                declaration["parameters"] = schema
            declarations.append(declaration)
        return [{"functionDeclarations": declarations}] if declarations else []

    @staticmethod
    def _to_generation_config(params: dict[str, Any]) -> dict[str, Any]:
        config: dict[str, Any] = {}
        mapping = {
            "temperature": "temperature",
            "top_p": "topP",
            "top_k": "topK",
            "max_tokens": "maxOutputTokens",
            "stop": "stopSequences",
        }
        for ours, theirs in mapping.items():
            if params.get(ours) is not None:
                config[theirs] = params[ours]
        return config

    @staticmethod
    def _parse(payload: dict[str, Any]) -> ProviderResponse:
        candidates = payload.get("candidates") or []
        if not candidates:
            # A prompt blocked by Vertex's own safety filter lands here. That is NOT the
            # agent behaving well — we learned nothing about it — so it must be an error.
            reason = payload.get("promptFeedback", {}).get("blockReason", "no candidates")
            raise ProviderError(f"Vertex returned no candidates ({reason})")

        candidate = candidates[0]
        parts = candidate.get("content", {}).get("parts") or []

        texts: list[str] = []
        calls: list[ToolCall] = []
        for part in parts:
            if isinstance(part.get("text"), str):
                texts.append(part["text"])
            call = part.get("functionCall")
            if isinstance(call, dict) and isinstance(call.get("name"), str):
                args = call.get("args")
                calls.append(
                    ToolCall(name=call["name"], arguments=args if isinstance(args, dict) else {})
                )

        return ProviderResponse(
            text="\n".join(texts).strip(),
            tool_calls=tuple(calls),
            model_version=str(payload.get("modelVersion", "")),
            usage=payload.get("usageMetadata", {}) or {},
            finish_reason=str(candidate.get("finishReason", "")),
        )

    # --- the call -----------------------------------------------------------------------

    def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        params: dict[str, Any],
    ) -> ProviderResponse:
        if not self.project:
            raise ProviderError(
                "No Vertex project configured. Set KEEL_VERTEX_PROJECT or GOOGLE_CLOUD_PROJECT."
            )

        body: dict[str, Any] = {"contents": messages}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        gemini_tools = self._to_gemini_tools(tools)
        if gemini_tools:
            body["tools"] = gemini_tools
        config = self._to_generation_config(params)
        if config:
            body["generationConfig"] = config

        url = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project}"
            f"/locations/{self.location}/publishers/google/models/{self.model}:generateContent"
        )

        try:
            response = httpx.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {self._token()}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Vertex request failed: {exc}") from exc

        if response.status_code != 200:
            # Truncate: an error body can echo the prompt back, and prompts are tenant data.
            raise ProviderError(
                f"Vertex returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("Vertex returned a non-JSON response") from exc

        return self._parse(payload)
