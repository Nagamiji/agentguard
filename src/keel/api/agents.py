import re
import uuid

from fastapi import APIRouter, Response, status
from fastapi.exceptions import HTTPException
from sqlalchemy import func, select

from keel.deps import DbSession, ReadOrg, WriteOrg
from keel.fingerprint import (
    FINGERPRINT_ALGO,
    ManifestError,
    compute_fingerprint,
    find_secrets,
)
from keel.models import Agent, AgentAlias, AgentVersion
from keel.schemas import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    AgentVersionCreate,
    AgentVersionOut,
    AliasOut,
    AliasUpsert,
)

router = APIRouter(prefix="/v1", tags=["agents"])

# A manifest is config, not a payload. The cap bounds both storage and the recursive
# canonicaliser's work on hostile input.
MAX_MANIFEST_BYTES = 256 * 1024


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "agent"


def _get_agent(agent_id: uuid.UUID, db: DbSession) -> Agent:
    """Fetch an agent, or 404.

    No organization_id filter: RLS scopes the query in Postgres, so another tenant's agent
    is simply invisible here and this raises 404 — which is also the right answer. A 403
    would confirm the row exists.
    """
    agent = db.execute(select(Agent).where(Agent.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return agent


@router.post("/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, org_id: WriteOrg, db: DbSession) -> AgentOut:
    # Plan validation
    from sqlalchemy import func

    from keel.models import Organization, Plan

    org = db.get(Organization, org_id)
    if org and org.plan_id:
        plan = db.get(Plan, org.plan_id)
    else:
        plan = db.execute(select(Plan).where(Plan.name == "free")).scalar_one_or_none()

    if plan:
        agent_count = (
            db.execute(
                select(func.count(Agent.id)).where(
                    Agent.organization_id == org_id, Agent.status == "active"
                )
            ).scalar()
            or 0
        )
        if plan.agent_limit >= 0 and agent_count >= plan.agent_limit:
            msg = (
                f"Agent limit reached ({plan.agent_limit}) for plan '{plan.name}'. "
                "Please upgrade to register more agents."
            )
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, msg)

    slug = payload.slug or _slugify(payload.name)
    existing = db.execute(select(Agent).where(Agent.slug == slug)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"An agent with slug '{slug}' already exists")

    agent = Agent(
        organization_id=org_id,
        name=payload.name,
        slug=slug,
        description=payload.description,
        framework=payload.framework,
        status="active",
        agent_metadata=payload.metadata,
    )
    db.add(agent)
    db.commit()
    return AgentOut.model_validate(agent)


@router.get("/agents", response_model=list[AgentOut])
def list_agents(org_id: ReadOrg, db: DbSession) -> list[AgentOut]:
    """List this organization's agents.

    As in projects.py, the absence of `.where(Agent.organization_id == org_id)` is
    deliberate: RLS scopes this inside Postgres, and tests/test_isolation.py fails loudly
    if it ever stops doing so.
    """
    rows = db.execute(select(Agent).order_by(Agent.created_at)).scalars().all()
    return [AgentOut.model_validate(r) for r in rows]


@router.get("/agents/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: uuid.UUID, org_id: ReadOrg, db: DbSession) -> AgentOut:
    return AgentOut.model_validate(_get_agent(agent_id, db))


@router.patch("/agents/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: uuid.UUID, payload: AgentUpdate, org_id: WriteOrg, db: DbSession
) -> AgentOut:
    """Update cosmetic fields. Never touches version data — versions are immutable."""
    agent = _get_agent(agent_id, db)

    if payload.name is not None:
        agent.name = payload.name
    if payload.description is not None:
        agent.description = payload.description
    if payload.status is not None:
        agent.status = payload.status
    if payload.metadata is not None:
        agent.agent_metadata = payload.metadata

    db.commit()
    return AgentOut.model_validate(agent)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: uuid.UUID, org_id: WriteOrg, db: DbSession) -> Response:
    agent = _get_agent(agent_id, db)
    db.delete(agent)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/agents/{agent_id}/versions", response_model=AgentVersionOut)
def create_agent_version(
    agent_id: uuid.UUID,
    payload: AgentVersionCreate,
    org_id: WriteOrg,
    db: DbSession,
    response: Response,
) -> AgentVersionOut:
    """Register a configuration snapshot.

    Returns 201 for a new fingerprint and **200 for one we already hold**: an unchanged
    config is not a new version. Langfuse creates a version on every save regardless of
    content and its users have asked for exactly this (langfuse discussion #2161).
    """
    agent = _get_agent(agent_id, db)

    # Reject secrets BEFORE hashing: the fingerprint is one-way, so a credential hashed
    # into it can never be redacted afterwards — only the whole row deleted.
    if leaked := find_secrets(payload.manifest):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Manifest appears to contain credentials ({', '.join(leaked)}). "
            "Reference secrets by name and inject them at runtime.",
        )

    try:
        fingerprint = compute_fingerprint(payload.manifest)
    except ManifestError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    existing = db.execute(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent.id,
            AgentVersion.fingerprint == fingerprint,
        )
    ).scalar_one_or_none()
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return AgentVersionOut.model_validate(existing)

    highest = db.execute(
        select(func.max(AgentVersion.sequence_number)).where(AgentVersion.agent_id == agent.id)
    ).scalar_one_or_none()

    version = AgentVersion(
        organization_id=org_id,
        agent_id=agent.id,
        sequence_number=(highest or 0) + 1,
        fingerprint=fingerprint,
        fingerprint_algo=FINGERPRINT_ALGO,
        manifest=payload.manifest,
    )
    db.add(version)
    db.commit()
    response.status_code = status.HTTP_201_CREATED
    return AgentVersionOut.model_validate(version)


@router.get("/agents/{agent_id}/versions", response_model=list[AgentVersionOut])
def list_agent_versions(
    agent_id: uuid.UUID, org_id: ReadOrg, db: DbSession
) -> list[AgentVersionOut]:
    agent = _get_agent(agent_id, db)
    rows = (
        db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent.id)
            .order_by(AgentVersion.sequence_number)
        )
        .scalars()
        .all()
    )
    return [AgentVersionOut.model_validate(r) for r in rows]


@router.get("/agents/{agent_id}/versions/{fingerprint}", response_model=AgentVersionOut)
def get_agent_version(
    agent_id: uuid.UUID, fingerprint: str, org_id: ReadOrg, db: DbSession
) -> AgentVersionOut:
    agent = _get_agent(agent_id, db)
    version = db.execute(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent.id,
            AgentVersion.fingerprint == fingerprint,
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent version not found")
    return AgentVersionOut.model_validate(version)


@router.put("/agents/{agent_id}/aliases/{name}", response_model=AliasOut)
def upsert_alias(
    agent_id: uuid.UUID,
    name: str,
    payload: AliasUpsert,
    org_id: WriteOrg,
    db: DbSession,
) -> AliasOut:
    """Point a named alias at a concrete version."""
    agent = _get_agent(agent_id, db)

    # RLS already hides other tenants' versions, so this lookup returning None covers both
    # "no such version" and "not yours" — and the alias check keeps a version from one
    # agent being pointed at by another's alias.
    version = db.execute(
        select(AgentVersion).where(
            AgentVersion.id == payload.version_id,
            AgentVersion.agent_id == agent.id,
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent version not found")

    alias = db.execute(
        select(AgentAlias).where(AgentAlias.agent_id == agent.id, AgentAlias.name == name)
    ).scalar_one_or_none()

    if alias is None:
        alias = AgentAlias(
            organization_id=org_id,
            agent_id=agent.id,
            name=name,
            version_id=version.id,
        )
        db.add(alias)
    else:
        alias.version_id = version.id

    db.commit()
    return AliasOut.model_validate(alias)


@router.get("/agents/{agent_id}/aliases/{name}", response_model=AgentVersionOut)
def resolve_alias(
    agent_id: uuid.UUID, name: str, org_id: ReadOrg, db: DbSession
) -> AgentVersionOut:
    """Resolve an alias to the concrete version it points at.

    Returns the version itself, fingerprint included, rather than a pointer the caller has
    to chase: MLflow #8078 is the cautionary tale, where an explicitly pinned version
    silently resolved to latest. A gate decision must record exactly what it evaluated.
    """
    agent = _get_agent(agent_id, db)
    alias = db.execute(
        select(AgentAlias).where(AgentAlias.agent_id == agent.id, AgentAlias.name == name)
    ).scalar_one_or_none()
    if alias is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alias not found")

    version = db.execute(
        select(AgentVersion).where(AgentVersion.id == alias.version_id)
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent version not found")
    return AgentVersionOut.model_validate(version)
