import time
from typing import Any

from fastapi import Depends, HTTPException

from keel.config import settings
from keel.db import get_redis_client
from keel.deps import CurrentOrg, DbSession


def rate_limited(limit_type: str) -> Any:
    """FastAPI dependency for tenant-aware rate limiting."""

    def dependency(
        org_id: CurrentOrg,
        db: DbSession,
    ) -> None:
        if not settings.rate_limit_enabled:
            return

        from sqlalchemy import select

        from keel.models import Organization

        org = db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
        if not org:
            return

        rate_limits = getattr(org, "rate_limits", {}) or {}

        # Determine rate (tokens per second) and burst
        if limit_type == "scans":
            default_rate = settings.rate_limit_scans_per_minute / 60.0
            default_burst = settings.rate_limit_scans_burst
        else:
            default_rate = settings.rate_limit_general_per_minute / 60.0
            default_burst = settings.rate_limit_general_burst

        override = rate_limits.get(limit_type, {})
        rate = override.get("rate", default_rate)
        burst = override.get("burst", default_burst)

        client = get_redis_client()
        key = f"rate_limit:{org_id}:{limit_type}"

        # Lua script for thread-safe atomic rate limiting
        LUA_LIMITER = """
        local key = KEYS[1]
        local rate = tonumber(ARGV[1])
        local burst = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local requested = 1

        local data = redis.call('HMGET', key, 'tokens', 'last_updated')
        local tokens = tonumber(data[1])
        local last_updated = tonumber(data[2])

        if not tokens then
            tokens = burst
            last_updated = now
        else
            local elapsed = math.max(0, now - last_updated)
            tokens = math.min(burst, tokens + (elapsed * rate))
        end

        local allowed = 0
        local retry_after = 0

        if tokens >= requested then
            tokens = tokens - requested
            allowed = 1
        else
            local needed = requested - tokens
            retry_after = math.ceil(needed / rate)
        end

        redis.call('HMSET', key, 'tokens', tokens, 'last_updated', now)
        redis.call('EXPIRE', key, math.ceil(burst / rate) + 60)

        return {allowed, retry_after}
        """

        script = client.register_script(LUA_LIMITER)

        try:
            allowed, retry_after = script(keys=[key], args=[rate, burst, time.time()])
        except Exception:
            # Fallback to allow request if Redis goes down, so we do not cause outage.
            return

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for '{limit_type}'. Retry in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

    return Depends(dependency)
