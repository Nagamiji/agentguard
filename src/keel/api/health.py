from fastapi import APIRouter
from fastapi.responses import JSONResponse

from keel import __version__
from keel.db import check_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: the process is up. No dependencies checked."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
def readyz() -> JSONResponse:
    """Readiness: dependencies reachable. 503 when the database is down."""
    db_ok = check_db()
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={"status": "ready" if db_ok else "degraded", "checks": {"database": db_ok}},
    )
