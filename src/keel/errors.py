from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_CONTENT_TYPE = "application/problem+json"


def problem(
    status: int,
    title: str,
    *,
    detail: str | None = None,
    type_: str = "about:blank",
    instance: str | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an RFC 9457 Problem Details response."""
    body: dict[str, Any] = {"type": type_, "title": title, "status": status}
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


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internals/stack traces to the client.
    return problem(
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred.",
        instance=request.url.path,
        request_id=getattr(request.state, "request_id", None),
    )
