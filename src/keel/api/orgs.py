import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from keel.deps import CurrentOrg, DbSession
from keel.models import ApiKey, Organization
from keel.schemas import (
    ApiKeyCreate,
    ApiKeyIssued,
    ApiKeyOut,
    OrgBootstrapOut,
    OrgCreate,
    OrgOut,
)
from keel.security import generate_api_key

router = APIRouter(prefix="/v1", tags=["organizations"])


@router.post("/orgs", response_model=OrgBootstrapOut, status_code=status.HTTP_201_CREATED)
def bootstrap_org(payload: OrgCreate, db: DbSession) -> OrgBootstrapOut:
    """Create an organization and issue its first API key.

    SECURITY [BE-01 scope]: this bootstrap endpoint is intentionally
    unauthenticated so a tenant can exist before it has a credential. Before any
    public exposure it must sit behind signup/authn + rate limiting (see BE-07,
    SEC-01). Tracked as a known gap, not an oversight.
    """
    org = Organization(name=payload.name)
    db.add(org)
    # flush() assigns the PK: column defaults (uuid4) are applied at INSERT time,
    # not at construction, so org.id is None until we flush.
    db.flush()

    full_key, prefix, key_hash = generate_api_key()
    db.add(ApiKey(organization_id=org.id, name="default", prefix=prefix, key_hash=key_hash))
    db.commit()

    return OrgBootstrapOut(organization=OrgOut.model_validate(org), api_key=full_key)


@router.post("/orgs/keys", response_model=ApiKeyIssued, status_code=status.HTTP_201_CREATED)
def issue_key(payload: ApiKeyCreate, org_id: CurrentOrg, db: DbSession) -> ApiKeyIssued:
    full_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(organization_id=org_id, name=payload.name, prefix=prefix, key_hash=key_hash)
    db.add(api_key)
    db.commit()
    return ApiKeyIssued(key=ApiKeyOut.model_validate(api_key), api_key=full_key)


@router.get("/orgs/keys", response_model=list[ApiKeyOut])
def list_keys(org_id: CurrentOrg, db: DbSession) -> list[ApiKeyOut]:
    rows = (
        db.execute(
            select(ApiKey).where(ApiKey.organization_id == org_id).order_by(ApiKey.created_at)
        )
        .scalars()
        .all()
    )
    return [ApiKeyOut.model_validate(r) for r in rows]


@router.delete("/orgs/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(key_id: uuid.UUID, org_id: CurrentOrg, db: DbSession) -> Response:
    """Revoke a key. Scoped by organization_id: you cannot revoke another org's key."""
    api_key = db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.organization_id == org_id)
    ).scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(UTC)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
