import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from keel.db import get_session
from keel.models import ApiKey
from keel.security import hash_api_key

DbSession = Annotated[Session, Depends(get_session)]


def require_org(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    """Authenticate the API key and bind the tenant to this transaction.

    After this dependency runs, Postgres Row-Level Security scopes every query on
    tenant tables to this organization — the app does not have to remember a
    WHERE clause, and a forgotten one cannot leak data across tenants.
    """
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

    # set_config(..., is_local=true) == SET LOCAL: scoped to this transaction and
    # parameterised (SET does not accept bind params, so this is the safe form).
    db.execute(
        text("SELECT set_config('app.current_org_id', :org, true)"),
        {"org": str(api_key.organization_id)},
    )
    return api_key.organization_id


CurrentOrg = Annotated[uuid.UUID, Depends(require_org)]
