import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from keel.deps import AdminOrg, DbSession
from keel.models import ApiKey, Organization, Plan
from keel.schemas import (
    ApiKeyCreate,
    ApiKeyIssued,
    ApiKeyOut,
    OnboardingInput,
    OnboardingOut,
    OrgBootstrapOut,
    OrgCreate,
    OrgOut,
    OrgStatusOut,
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
    db.add(
        ApiKey(
            organization_id=org.id, name="default", prefix=prefix, key_hash=key_hash, scopes=["*"]
        )
    )
    db.commit()

    return OrgBootstrapOut(organization=OrgOut.model_validate(org), api_key=full_key)


@router.post("/orgs/keys", response_model=ApiKeyIssued, status_code=status.HTTP_201_CREATED)
def issue_key(payload: ApiKeyCreate, org_id: AdminOrg, db: DbSession) -> ApiKeyIssued:
    full_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(
        organization_id=org_id,
        name=payload.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=payload.scopes,
    )
    db.add(api_key)
    db.commit()
    return ApiKeyIssued(key=ApiKeyOut.model_validate(api_key), api_key=full_key)


@router.get("/orgs/keys", response_model=list[ApiKeyOut])
def list_keys(org_id: AdminOrg, db: DbSession) -> list[ApiKeyOut]:
    rows = (
        db.execute(
            select(ApiKey).where(ApiKey.organization_id == org_id).order_by(ApiKey.created_at)
        )
        .scalars()
        .all()
    )
    return [ApiKeyOut.model_validate(r) for r in rows]


@router.delete("/orgs/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(key_id: uuid.UUID, org_id: AdminOrg, db: DbSession) -> Response:
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


@router.post("/onboarding", response_model=OnboardingOut, status_code=status.HTTP_201_CREATED)
def onboard_customer(payload: OnboardingInput, db: DbSession) -> OnboardingOut:
    """Self-serve customer onboarding: provisions an organization and credentials."""
    # 1. Create Organization
    org = Organization(name=payload.organization_name)
    db.add(org)
    db.flush()

    # 2. Link default "free" plan
    free_plan = db.execute(select(Plan).where(Plan.name == "free")).scalar_one_or_none()
    if free_plan:
        org.plan_id = free_plan.id

    # 3. Create initial API key
    full_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(
        organization_id=org.id,
        name="onboarding-key",
        prefix=prefix,
        key_hash=key_hash,
        scopes=["*"],
    )
    db.add(api_key)
    db.commit()

    next_steps = (
        "Welcome to AgentGuard! To integrate security scans into your workflow:\n"
        "1. Install the AgentGuard CLI: pip install agentguard-cli\n"
        "2. Export your credentials in your terminal or CI environment:\n"
        f"   export AGENTGUARD_API_KEY={full_key}\n"
        "3. Scaffold your configuration in your repository root:\n"
        "   agentguard init\n"
        "4. Run a security scan:\n"
        "   agentguard scan --agent-slug [agent-name]"
    )

    return OnboardingOut(
        organization_id=org.id,
        api_key=full_key,
        next_steps=next_steps,
    )


# ---------------------------------------------------------------------------
# Admin: organization lifecycle
# ---------------------------------------------------------------------------


@router.post(
    "/admin/orgs/{org_id}/activate",
    response_model=OrgStatusOut,
    tags=["admin"],
)
def activate_org(org_id: uuid.UUID, caller_org: AdminOrg, db: DbSession) -> OrgStatusOut:
    """Activate a pending or suspended organization (admin only)."""
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if org.status == "deleted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot activate a deleted organization")
    org.status = "active"
    db.commit()
    return OrgStatusOut(id=org.id, name=org.name, status=org.status)


@router.post(
    "/admin/orgs/{org_id}/suspend",
    response_model=OrgStatusOut,
    tags=["admin"],
)
def suspend_org(org_id: uuid.UUID, caller_org: AdminOrg, db: DbSession) -> OrgStatusOut:
    """Suspend an organization — all API key authentication will be rejected."""
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if org.status == "deleted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot suspend a deleted organization")
    org.status = "suspended"
    db.commit()
    return OrgStatusOut(id=org.id, name=org.name, status=org.status)
