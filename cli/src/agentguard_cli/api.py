"""A thin AgentGuard API client.

Wraps any httpx-compatible client (a real `httpx.Client` in production, or FastAPI's
`TestClient` in tests) so the whole scan flow is exercisable in-process without a network.
"""

from __future__ import annotations

from typing import Any, Protocol


class HttpLike(Protocol):
    """The slice of httpx.Client / FastAPI TestClient this CLI uses. Both satisfy it."""

    def get(self, url: str, *, params: Any = ..., headers: Any = ...) -> Any: ...
    def post(self, url: str, *, json: Any = ..., params: Any = ..., headers: Any = ...) -> Any: ...


class ApiError(RuntimeError):
    """A transport or HTTP error talking to AgentGuard. Callers treat this as fail-closed."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    def __init__(self, http: HttpLike, api_key: str) -> None:
        self._http = http
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = getattr(self._http, method)(url, headers=self._headers, **kwargs)
        except Exception as exc:  # httpx.HTTPError, connection refused, DNS, timeouts…
            raise ApiError(f"could not reach AgentGuard at {url}: {exc}") from exc
        if resp.status_code >= 400:
            raise ApiError(
                f"{method.upper()} {url} -> HTTP {resp.status_code}: {resp.text[:200]}",
                resp.status_code,
            )
        data: dict[str, Any] = resp.json()
        return data

    def create_version(self, agent: str, manifest: dict[str, Any]) -> dict[str, Any]:
        return self._request("post", f"/v1/agents/{agent}/versions", json={"manifest": manifest})

    def import_library(self, agent: str) -> dict[str, Any]:
        return self._request("post", f"/v1/agents/{agent}/scenarios/import")

    def create_run(
        self, agent: str, version_id: str, runner: str, environment: str | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"version_id": version_id, "runner": runner}
        if environment is not None:
            body["environment"] = environment
        return self._request("post", f"/v1/agents/{agent}/runs", json=body)

    def get_gate(self, agent: str, fingerprint: str) -> dict[str, Any]:
        return self._request("get", f"/v1/agents/{agent}/gate", params={"fingerprint": fingerprint})

    def get_risk(self, agent: str, fingerprint: str) -> dict[str, Any]:
        return self._request("get", f"/v1/agents/{agent}/risk", params={"fingerprint": fingerprint})

    def get_policy(self, agent: str, environment: str | None) -> dict[str, Any]:
        params = {"environment": environment} if environment is not None else {}
        return self._request("get", f"/v1/agents/{agent}/policy", params=params)

    def get_version_by_fingerprint(self, agent: str, fingerprint: str) -> dict[str, Any]:
        return self._request("get", f"/v1/agents/{agent}/versions/{fingerprint}")

    def get_agent(self, agent: str) -> dict[str, Any]:
        return self._request("get", f"/v1/agents/{agent}")
