"""Provisioning gate for the unauthenticated tenant-creation endpoints (S7).

`POST /v1/orgs` and `POST /v1/onboarding` create an organization and mint its first API key
*before any credential exists*, so `require_permission` cannot protect them — the exposure is
before authorization. Left open, anyone could mint unlimited orgs and full-access keys.

This guard closes that surface with two independent controls:

1. A shared **provisioning secret** (`X-Provisioning-Key` == `KEEL_ONBOARDING_SECRET`). When the
   secret is configured it is required in every environment. When it is *unset*, provisioning is
   allowed only in dev and **disabled in production** — fail-closed by default, so a deploy that
   forgets to configure the secret cannot accidentally expose open onboarding.
2. A per-IP **rate limit** (token bucket in Redis). Deliberately **fails closed** if the limiter
   store is unavailable: an abuse-prone anonymous endpoint must not fail open (contrast the
   authenticated scan limiter in keel/rate_limit.py, which fails open to avoid a tenant outage).

IP note: the client address comes from `request.client` (or the first `X-Forwarded-For` hop).
Without a trusted-proxy config, XFF is caller-controlled; the secret is the primary control and
the rate limit is defence-in-depth.
"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request, status

from keel.config import settings
from keel.db import get_redis_client

_PROD_ENVS = frozenset({"prod", "production", "staging"})

# Token-bucket limiter (mirrors keel/rate_limit.py) but keyed per IP and fail-closed.
_LUA_LIMITER = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
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
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
else
    retry_after = math.ceil((1 - tokens) / rate)
end
redis.call('HMSET', key, 'tokens', tokens, 'last_updated', now)
redis.call('EXPIRE', key, math.ceil(burst / rate) + 60)
return {allowed, retry_after}
"""


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_secret(request: Request) -> None:
    if settings.onboarding_secret:
        presented = request.headers.get("x-provisioning-key", "")
        # Length-leaking is not a concern here (secret compared, not a per-user token), but a
        # constant-time compare is cheap and avoids a timing oracle on the shared secret.
        import hmac

        if not hmac.compare_digest(presented, settings.onboarding_secret):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing X-Provisioning-Key.",
            )
        return
    # No secret configured: allowed in dev, disabled in production.
    if settings.app_env.lower() in _PROD_ENVS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant provisioning is disabled: set KEEL_ONBOARDING_SECRET to enable it.",
        )


def _check_rate_limit(request: Request) -> None:
    if not settings.rate_limit_enabled:
        return
    per_hour = max(1, settings.onboarding_rate_limit_per_hour)
    rate = per_hour / 3600.0
    burst = per_hour
    key = f"rate_limit:onboarding:{_client_ip(request)}"
    try:
        client = get_redis_client()
        script = client.register_script(_LUA_LIMITER)
        allowed, retry_after = script(keys=[key], args=[rate, burst, time.time()])
    except Exception as exc:
        # Fail CLOSED: an unauthenticated abuse surface must not open up when Redis is down.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Provisioning temporarily unavailable (rate limiter offline).",
        ) from exc
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many provisioning requests. Retry in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def provisioning_guard(request: Request) -> None:
    """FastAPI dependency gating an unauthenticated tenant-creation endpoint.

    Runs the provisioning-secret check, then the per-IP rate limit.
    """
    _check_secret(request)
    _check_rate_limit(request)
