import uuid
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from keel.db import get_session
from keel.models import ApiKey
from keel.security import hash_api_key

DbSession = Annotated[Session, Depends(get_session)]


def require_permission(*required_scopes: str) -> Any:
    """Dependency builder that authenticates the API key, checks scopes, and binds RLS."""

    def dependency(
        db: DbSession,
        authorization: Annotated[str | None, Header()] = None,
    ) -> uuid.UUID:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Missing or malformed Authorization header"
            )
        token = authorization.split(" ", 1)[1].strip()

        api_key = db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == hash_api_key(token),
                ApiKey.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        if api_key is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API key")

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

        # Set org context variable
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
