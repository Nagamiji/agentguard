import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from keel.context import (
    org_id_var,
    request_id_var,
    run_id_var,
    set_org_id,
    set_request_id,
    set_run_id,
)
from keel.metrics import metrics


def metric_path_label(path: str, path_params: Mapping[str, Any], matched: bool) -> str:
    """Low-cardinality label for the `path` metric dimension.

    A raw request path carries IDs (`/v1/agents/<uuid>/gate`), so using it verbatim as a
    Prometheus label makes the time-series set unbounded. Collapse each matched path-param
    value back to its `{name}` placeholder (segment-wise, so a value can never be replaced
    inside a static segment). Unmatched requests (404s — a scanner can invent infinite
    paths) collapse to a single `"unmatched"` bucket; matched paths with no params are
    already static, so they pass through unchanged.
    """
    if path_params:
        value_to_key = {str(v): k for k, v in path_params.items()}
        segments = path.split("/")
        return "/".join(f"{{{value_to_key[s]}}}" if s in value_to_key else s for s in segments)
    return path if matched else "unmatched"


class ContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id to every request, and echo it back.

    Tenant context is deliberately NOT set here. It comes from `require_org` (keel/deps.py),
    which resolves the organization from an API key and binds it to the database
    transaction, where RLS enforces it. This middleware previously also read an `X-Org-ID`
    header into request state — a client-controlled, tenant-shaped value that authorised
    nothing but sat one careless `getattr` away from looking authoritative. Removed in
    BE-02: the only tenant identity is the one the database is enforcing.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id

        req_token = set_request_id(request_id)
        org_token = set_org_id(None)
        run_token = set_run_id(None)

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration = time.perf_counter() - start_time
            # Routing runs downstream of this middleware but mutates the *same* scope dict,
            # so the matched route's path_params/endpoint are readable here after call_next.
            path_label = metric_path_label(
                request.url.path,
                request.scope.get("path_params") or {},
                request.scope.get("endpoint") is not None,
            )
            metrics.http_requests_total.inc(
                labels={
                    "method": request.method,
                    "path": path_label,
                    "status": str(response.status_code),
                }
            )
            metrics.http_request_duration_seconds.observe(
                duration, labels={"method": request.method, "path": path_label}
            )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(req_token)
            org_id_var.reset(org_token)
            run_id_var.reset(run_token)
