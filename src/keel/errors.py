import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("keel.errors")

PROBLEM_CONTENT_TYPE = "application/problem+json"

# Map HTTP status codes to stable machine-readable error codes.
_STATUS_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    402: "PAYMENT_REQUIRED",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMIT_EXCEEDED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def problem(
    status: int,
    title: str,
    *,
    code: str | None = None,
    detail: str | None = None,
    type_: str = "about:blank",
    instance: str | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an RFC 9457 Problem Details response with an AgentGuard error code."""
    resolved_code = code or _STATUS_CODE_MAP.get(status, "INTERNAL_ERROR")
    body: dict[str, Any] = {
        "type": type_,
        "title": title,
        "status": status,
        "error": {
            "code": resolved_code,
            "message": str(title),
            "request_id": request_id,
        },
    }
    if detail:
        body["detail"] = detail
    if instance:
        body["instance"] = instance
    if request_id:
        body["trace_id"] = request_id
    return JSONResponse(
        status_code=status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    status = exc.status_code if isinstance(exc, StarletteHTTPException) else 500
    title = exc.detail if isinstance(exc, StarletteHTTPException) else "HTTP error"
    headers = getattr(exc, "headers", None)
    return problem(
        status=status,
        title=str(title),
        instance=request.url.path,
        request_id=getattr(request.state, "request_id", None),
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert Pydantic RequestValidationError into a standardised Problem Details response."""
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    detail_parts = [f"{' -> '.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in errors]
    return problem(
        status=422,
        title="Request validation failed",
        code="VALIDATION_ERROR",
        detail="; ".join(detail_parts) if detail_parts else None,
        instance=request.url.path,
        request_id=getattr(request.state, "request_id", None),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    # Log the failure server-side with the traceback and request context. This is the only
    # place an unhandled 500 becomes visible to operators — the client only ever sees the
    # generic body below. request_id is passed explicitly: this handler runs in the outer
    # ServerErrorMiddleware, AFTER ContextMiddleware has reset the contextvars, so the
    # ContextFilter can no longer supply it (an explicit `extra` wins over the filter).
    # Only low-risk request metadata is logged — never headers, body, or query string
    # (which may carry secrets). logging.error swallows any handler error internally, so it
    # cannot turn one failure into two.
    logger.error(
        "unhandled_exception",
        exc_info=exc,
        extra={"request_id": request_id, "method": request.method, "path": request.url.path},
    )
    # Never leak internals/stack traces to the client.
    return problem(
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred.",
        instance=request.url.path,
        request_id=request_id,
    )
