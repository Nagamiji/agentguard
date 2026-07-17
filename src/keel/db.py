from collections.abc import Iterator

import redis
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from keel.config import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_redis_pool: redis.ConnectionPool | None = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session() -> Iterator[Session]:
    get_engine()
    if _session_factory is None:
        raise RuntimeError("session factory not initialized")
    with _session_factory() as session:
        yield session


def check_db() -> bool:
    """Liveness check for /readyz. Returns False (not raises) when the DB is unreachable."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


def get_redis_client() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return redis.Redis(connection_pool=_redis_pool)
