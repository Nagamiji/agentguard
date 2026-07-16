import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


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
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
