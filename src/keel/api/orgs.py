import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from keel.audit import record_audit_event
from keel.deps import AdminOrg, DbSession
from keel.models import ApiKey, Organization, Plan
from keel.provisioning import provisioning_guard
from keel.roles import scopes_for_role, undelegatable_scopes
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


@router.post(
    "/orgs",
    response_model=OrgBootstrapOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(provisioning_guard)],
)
def bootstrap_org(payload: OrgCreate, db: DbSession) -> OrgBootstrapOut:
    """Create an organization and issue its first (administrative) API key.

    SECURITY (S7): this endpoint runs *before* any credential exists, so it cannot be
    authorized by an API key. It is instead gated by `provisioning_guard` — a shared
    provisioning secret (required whenever configured; fail-closed in production) plus a
    per-IP rate limit. The bootstrap key is the org's administrative root, so it carries the
    explicit `admin` scopes (read/write/scan/admin) — not the `*` wildcard, which would also
    grant any scope added in the future.
    """
    org = Organization(name=payload.name)
    db.add(org)
    # flush() assigns the PK: column defaults (uuid4) are applied at INSERT time,
    # not at construction, so org.id is None until we flush.
    db.flush()

    full_key, prefix, key_hash = generate_api_key()
    db.add(
        ApiKey(
            organization_id=org.id,
            name="default",
            prefix=prefix,
            key_hash=key_hash,
            scopes=scopes_for_role("admin"),
            role="admin",
            created_by="bootstrap",
        )
    )
    db.commit()

    return OrgBootstrapOut(organization=OrgOut.model_validate(org), api_key=full_key)


@router.post("/orgs/keys", response_model=ApiKeyIssued, status_code=status.HTTP_201_CREATED)
def issue_key(
    payload: ApiKeyCreate, request: Request, org_id: AdminOrg, db: DbSession
) -> ApiKeyIssued:
    actor = getattr(request.state, "actor", None)
    # The schema's model_validator guarantees scopes are resolved (from role or explicit)
    # or the request is rejected as 422 — so a None here would be an internal invariant
    # break, not an implicit wildcard. Fail closed rather than mint anything.
    scopes = payload.scopes
    if scopes is None:  # pragma: no cover - unreachable while resolve_scopes holds
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide a 'role' or explicit 'scopes'"
        )

    # Delegation boundary: a caller can never mint a key with more authority than it holds.
    caller_scopes = getattr(request.state, "scopes", [])
    excess = undelegatable_scopes(caller_scopes, scopes)
    if excess:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Cannot grant scopes you do not hold: {sorted(excess)}",
        )

    full_key, prefix, key_hash = generate_api_key()
    expires_at = (
        datetime.now(UTC) + timedelta(days=payload.expires_in_days)
        if payload.expires_in_days is not None
        else None
    )
    api_key = ApiKey(
        organization_id=org_id,
        name=payload.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=scopes,
        role=payload.role,
        expires_at=expires_at,
        created_by=actor,
    )
    db.add(api_key)
    record_audit_event(
        db,
        organization_id=org_id,
        actor=actor,
        action="api_key.issued",
        resource_type="api_key",
        resource_id=str(api_key.id),
        metadata={"name": payload.name, "scopes": scopes, "role": payload.role},
    )
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
def revoke_key(key_id: uuid.UUID, request: Request, org_id: AdminOrg, db: DbSession) -> Response:
    """Revoke a key. Scoped by organization_id: you cannot revoke another org's key."""
    api_key = db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.organization_id == org_id)
    ).scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(UTC)
        record_audit_event(
            db,
            organization_id=org_id,
            actor=getattr(request.state, "actor", None),
            action="api_key.revoked",
            resource_type="api_key",
            resource_id=str(api_key.id),
            metadata={"name": api_key.name},
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/onboarding",
    response_model=OnboardingOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(provisioning_guard)],
)
def onboard_customer(payload: OnboardingInput, db: DbSession) -> OnboardingOut:
    """Self-serve customer onboarding: provisions an organization and credentials.

    SECURITY (S7): gated by `provisioning_guard` (provisioning secret + per-IP rate limit),
    since it creates a tenant before any credential exists. The initial key is least-privilege
    — the `developer` role (read/write/scan) — so a self-serve tenant can register agents,
    author policies, and run scans, but cannot manage API keys or the org itself. An `admin`
    key is granted separately (by an existing admin key or the operator).
    """
    # 1. Create Organization
    org = Organization(name=payload.organization_name)
    db.add(org)
    db.flush()

    # 2. Link default "free" plan
    free_plan = db.execute(select(Plan).where(Plan.name == "free")).scalar_one_or_none()
    if free_plan:
        org.plan_id = free_plan.id

    # 3. Create initial API key (least privilege: developer, not wildcard)
    full_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(
        organization_id=org.id,
        name="onboarding-key",
        prefix=prefix,
        key_hash=key_hash,
        scopes=scopes_for_role("developer"),
        role="developer",
        created_by="onboarding",
    )
    db.add(api_key)
    db.commit()

    next_steps = (
        "Welcome to AgentGuard! To integrate security scans into your workflow:\n"
        "1. Install the AgentGuard CLI: pip install agentguard-dev\n"
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
def activate_org(
    org_id: uuid.UUID, request: Request, caller_org: AdminOrg, db: DbSession
) -> OrgStatusOut:
    """Activate a pending or suspended organization (admin only)."""
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if org.status == "deleted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot activate a deleted organization")
    org.status = "active"
    record_audit_event(
        db,
        organization_id=caller_org,
        actor=getattr(request.state, "actor", None),
        action="organization.activated",
        resource_type="organization",
        resource_id=str(org_id),
    )
    db.commit()
    return OrgStatusOut(id=org.id, name=org.name, status=org.status)


@router.post(
    "/admin/orgs/{org_id}/suspend",
    response_model=OrgStatusOut,
    tags=["admin"],
)
def suspend_org(
    org_id: uuid.UUID, request: Request, caller_org: AdminOrg, db: DbSession
) -> OrgStatusOut:
    """Suspend an organization — all API key authentication will be rejected."""
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if org.status == "deleted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot suspend a deleted organization")
    org.status = "suspended"
    record_audit_event(
        db,
        organization_id=caller_org,
        actor=getattr(request.state, "actor", None),
        action="organization.suspended",
        resource_type="organization",
        resource_id=str(org_id),
    )
    db.commit()
    return OrgStatusOut(id=org.id, name=org.name, status=org.status)
