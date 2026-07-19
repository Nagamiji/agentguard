import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from keel.db import get_session
from keel.models import ApiKey
from keel.security import hash_api_key

DbSession = Annotated[Session, Depends(get_session)]

# How stale last_used_at may get before we refresh it. Bounds the extra write to at most
# once per minute per key so authentication is not a guaranteed database write.
_LAST_USED_THROTTLE = timedelta(seconds=60)


def require_permission(*required_scopes: str) -> Any:
    """Dependency builder that authenticates the API key, checks scopes, and binds RLS."""

    def dependency(
        request: Request,
        db: DbSession,
        authorization: Annotated[str | None, Header()] = None,
    ) -> uuid.UUID:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Missing or malformed Authorization header"
            )
        token = authorization.split(" ", 1)[1].strip()
        if not token:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Missing or malformed Authorization header"
            )

        api_key = db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == hash_api_key(token),
                ApiKey.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        if api_key is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API key")

        now = datetime.now(UTC)

        # Expiry is enforced here, not in the query, so an expired key gets a clear
        # message instead of looking like an unknown key.
        if api_key.expires_at is not None and api_key.expires_at <= now:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key has expired")

        # Organization lifecycle check: suspended orgs are completely blocked.
        from keel.models import Organization

        org = db.get(Organization, api_key.organization_id)
        if org is not None and org.status == "suspended":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Organization is suspended. Contact support to reactivate your account.",
            )

        # Scope check: if '*' is present, all scopes are allowed.
        # Otherwise, the key must have at least one of the required_scopes (if any are specified).
        key_scopes = getattr(api_key, "scopes", ["*"])
        if required_scopes and "*" not in key_scopes:
            if not any(s in key_scopes for s in required_scopes):
                needed = ", ".join(required_scopes)
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    f"Scope forbidden: key lacks required permission (needs one of: {needed})",
                )

        # Refresh last_used_at at most once per throttle window. This commit must happen
        # BEFORE the SET LOCAL below: committing ends the transaction, which would discard
        # a transaction-local setting. Here there is no request work pending yet (the
        # endpoint body has not run), so committing only persists last_used_at.
        last_used = api_key.last_used_at
        if last_used is None or (now - last_used) > _LAST_USED_THROTTLE:
            api_key.last_used_at = now
            db.commit()

        # Record who is acting, for the audit trail (keel/audit.py). The key prefix, never
        # the secret. request.state survives from this dependency into the handler (a shared
        # per-request object), unlike a contextvar set inside a threadpool-run dependency.
        request.state.actor = api_key.prefix
        # Expose the caller's scopes so endpoints can enforce delegation boundaries
        # (a key may never grant more than its creator holds) without a second key lookup.
        request.state.scopes = list(key_scopes)

        from keel.context import set_org_id

        set_org_id(str(api_key.organization_id))

        # set_config(..., is_local=true) == SET LOCAL: scoped to this transaction and
        # parameterised (SET does not accept bind params, so this is the safe form).
        db.execute(
            text("SELECT set_config('app.current_org_id', :org, true)"),
            {"org": str(api_key.organization_id)},
        )
        return api_key.organization_id

    return Depends(dependency)


# For backward compatibility / general endpoints
require_org = require_permission()
CurrentOrg = Annotated[uuid.UUID, require_org]

ReadOrg = Annotated[uuid.UUID, require_permission("read")]
WriteOrg = Annotated[uuid.UUID, require_permission("write")]
ScanOrg = Annotated[uuid.UUID, require_permission("scan")]
AdminOrg = Annotated[uuid.UUID, require_permission("admin")]
