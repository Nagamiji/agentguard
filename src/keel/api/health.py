from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from keel import __version__
from keel.db import check_db, get_redis_client
from keel.metrics import metrics

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: the process is up. No dependencies checked."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
def readyz() -> JSONResponse:
    """Readiness: dependencies reachable. 503 when the database or redis is down."""
    db_ok = check_db()
    redis_ok = False
    try:
        get_redis_client().ping()
        redis_ok = True
    except Exception:  # noqa: S110
        pass

    ok = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": "ready" if ok else "degraded",
            "checks": {"database": db_ok, "redis": redis_ok},
        },
    )


@router.get("/metrics")
def get_metrics() -> Response:
    """Expose Prometheus-formatted metrics."""
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")
