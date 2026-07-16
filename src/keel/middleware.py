import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id + tenant context to every request.

    Real authentication (API key -> organization) lands in BE-01; this establishes
    the contract that every request carries a request_id and an org scope.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        request.state.org_id = request.headers.get("X-Org-ID")
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
