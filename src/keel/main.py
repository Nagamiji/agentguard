from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from keel import __version__
from keel.api.agents import router as agents_router
from keel.api.dashboard import router as dashboard_router
from keel.api.evals import router as evals_router
from keel.api.health import router as health_router
from keel.api.orgs import router as orgs_router
from keel.api.policies import router as policies_router
from keel.api.projects import router as projects_router
from keel.config import settings
from keel.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from keel.logging import configure_logging
from keel.middleware import ContextMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.app_env == "production":
        missing = []
        if not settings.secret_key:
            missing.append("KEEL_SECRET_KEY")
        if not settings.api_key_hash_secret:
            missing.append("KEEL_API_KEY_HASH_SECRET")
        if missing:
            raise RuntimeError(f"Missing critical production configurations: {', '.join(missing)}")
    yield


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(title="Keel Platform", version=__version__, lifespan=lifespan)
    app.add_middleware(ContextMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health_router)
    app.include_router(orgs_router)
    app.include_router(projects_router)
    app.include_router(agents_router)
    app.include_router(evals_router)
    app.include_router(policies_router)
    app.include_router(dashboard_router)
    return app


app = create_app()
