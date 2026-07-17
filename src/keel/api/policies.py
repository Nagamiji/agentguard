import uuid

from fastapi import APIRouter, Query, Response, status
from fastapi.exceptions import HTTPException
from sqlalchemy import select

from keel.api.lookups import get_agent_or_404
from keel.api.policy_service import effective_policy
from keel.deps import DbSession, ReadOrg, WriteOrg
from keel.models import AgentVersion, Policy, PolicyVersion
from keel.policy import PolicyError, fingerprint_rules, validate_rules
from keel.policy.resolver import effective_values
from keel.schemas import (
    CompiledPolicyOut,
    EffectiveRule,
    PolicyCreate,
    PolicyCreated,
    PolicyDetail,
    PolicyOut,
    PolicyVersionCreate,
    PolicyVersionOut,
)

router = APIRouter(prefix="/v1", tags=["policies"])


def _resolve_scope_id(payload: PolicyCreate, org_id: uuid.UUID, db: DbSession) -> uuid.UUID:
    if payload.scope_type == "project":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "project-scoped policies are not supported yet: agents are not linked to projects "
            "(see docs/architecture/adr-0012-policy-engine.md).",
        )
    if payload.scope_type == "organization":
        # An org policy always attaches to the caller's own org; ignore any provided id.
        return org_id
    # agent scope
    if payload.scope_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "scope_id (an agent id) is required")
    # RLS makes another tenant's agent invisible, so this doubles as an ownership check.
    get_agent_or_404(payload.scope_id, db)
    return payload.scope_id


def _existing_policy(
    scope_type: str, scope_id: uuid.UUID, environment: str | None, db: DbSession
) -> Policy | None:
    condition = (
        Policy.environment.is_(None) if environment is None else Policy.environment == environment
    )
    return db.execute(
        select(Policy).where(
            Policy.scope_type == scope_type, Policy.scope_id == scope_id, condition
        )
    ).scalar_one_or_none()


@router.post("/policies", response_model=PolicyCreated, status_code=status.HTTP_201_CREATED)
def create_policy(payload: PolicyCreate, org_id: WriteOrg, db: DbSession) -> PolicyCreated:
    scope_id = _resolve_scope_id(payload, org_id, db)

    try:
        validate_rules(payload.rules)
    except PolicyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if _existing_policy(payload.scope_type, scope_id, payload.environment, db) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A policy already exists for this scope and environment. POST a new version to "
            "change its rules (history is immutable).",
        )

    policy = Policy(
        organization_id=org_id,
        scope_type=payload.scope_type,
        scope_id=scope_id,
        environment=payload.environment,
        name=payload.name,
    )
    db.add(policy)
    db.flush()  # need policy.id for the first version

    version = PolicyVersion(
        organization_id=org_id,
        policy_id=policy.id,
        sequence_number=1,
        rules=payload.rules,
        fingerprint=fingerprint_rules(payload.rules),
        note=payload.note,
    )
    db.add(version)
    db.commit()

    # Built from held objects, not re-queried (the tenant GUC is discarded by commit — see
    # keel/api/evals.py create_run for the full note).
    return PolicyCreated(
        policy=PolicyOut.model_validate(policy), version=PolicyVersionOut.model_validate(version)
    )


@router.post(
    "/policies/{policy_id}/versions",
    response_model=PolicyVersionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_policy_version(
    policy_id: uuid.UUID,
    payload: PolicyVersionCreate,
    org_id: WriteOrg,
    db: DbSession,
    response: Response,
) -> PolicyVersionOut:
    """Append an immutable version. Same rules as the current tip dedupe (200), not a new row."""
    policy = db.execute(select(Policy).where(Policy.id == policy_id)).scalar_one_or_none()
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Policy not found")

    try:
        validate_rules(payload.rules)
    except PolicyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    fingerprint = fingerprint_rules(payload.rules)
    existing = db.execute(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == policy.id, PolicyVersion.fingerprint == fingerprint
        )
    ).scalar_one_or_none()
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return PolicyVersionOut.model_validate(existing)

    highest = db.execute(
        select(PolicyVersion.sequence_number)
        .where(PolicyVersion.policy_id == policy.id)
        .order_by(PolicyVersion.sequence_number.desc())
        .limit(1)
    ).scalar_one_or_none()

    version = PolicyVersion(
        organization_id=org_id,
        policy_id=policy.id,
        sequence_number=(highest or 0) + 1,
        rules=payload.rules,
        fingerprint=fingerprint,
        note=payload.note,
    )
    db.add(version)
    db.commit()
    response.status_code = status.HTTP_201_CREATED
    return PolicyVersionOut.model_validate(version)


@router.get("/policies", response_model=list[PolicyOut])
def list_policies(org_id: ReadOrg, db: DbSession) -> list[PolicyOut]:
    rows = db.execute(select(Policy).order_by(Policy.created_at)).scalars().all()
    return [PolicyOut.model_validate(p) for p in rows]


@router.get("/policies/{policy_id}", response_model=PolicyDetail)
def get_policy(policy_id: uuid.UUID, org_id: ReadOrg, db: DbSession) -> PolicyDetail:
    policy = db.execute(select(Policy).where(Policy.id == policy_id)).scalar_one_or_none()
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Policy not found")
    versions = (
        db.execute(
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy.id)
            .order_by(PolicyVersion.sequence_number)
        )
        .scalars()
        .all()
    )
    detail = PolicyDetail.model_validate(policy)
    detail.versions = [PolicyVersionOut.model_validate(v) for v in versions]
    return detail


@router.get("/agents/{agent_id}/policy", response_model=CompiledPolicyOut)
def get_agent_policy(
    agent_id: uuid.UUID,
    org_id: ReadOrg,
    db: DbSession,
    environment: str | None = Query(default=None, description="Which environment's policy."),
) -> CompiledPolicyOut:
    """Preview the effective, compiled policy for an agent — exactly what a scan will enforce.

    Shows provenance (which scope set each rule, so a lower scope loosening a higher one is
    visible) and which declared rules are deferred to runtime.
    """
    agent = get_agent_or_404(agent_id, db)

    latest = db.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent.id)
        .order_by(AgentVersion.sequence_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    manifest = latest.manifest if latest is not None else {}

    resolved, compiled = effective_policy(db, org_id, agent.id, environment, manifest)

    return CompiledPolicyOut(
        environment=environment,
        fingerprint=fingerprint_rules(effective_values(resolved)),
        effective={k: EffectiveRule(value=r.value, source=r.source) for k, r in resolved.items()},
        derived_checks=compiled.derived_checks,
        manifest_findings=compiled.manifest_findings,
        deferred_runtime=compiled.deferred_runtime,
    )
