import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    """The tenant root. Every tenant-scoped row carries organization_id."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Agent(Base):
    """A registered AI agent — stable identity, mutable metadata.

    Renaming must never break references, so `slug` is the durable handle and `name` is
    free to change. Protected by Row-Level Security (migration 0002).
    """

    __tablename__ = "agents"
    __table_args__ = (
        # The slug is the stable handle, so it must be unique per tenant — not globally,
        # which would leak the existence of other orgs' agents through collisions.
        UniqueConstraint("organization_id", "slug", name="uq_agents_org_slug"),
        # `status` is the lifecycle of THIS RECORD only. It must never encode deployment
        # state: MLflow shipped a stage enum that conflated lifecycle, environment and
        # access control, and deprecated it (mlflow#10336). Deployment lives in
        # agent_aliases.
        CheckConstraint("status IN ('active', 'archived')", name="ck_agents_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    framework: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    agent_metadata: Mapped[dict[str, Any]] = mapped_column(
        # `metadata` is reserved by SQLAlchemy's Declarative API, so the attribute is
        # renamed while the column keeps the name the API exposes.
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class AgentVersion(Base):
    """An immutable configuration snapshot of an agent.

    Never updated after insert — there is no update endpoint, and `manifest` is stored as
    inert JSONB that is never deserialised into executable objects. LangSmith's
    GHSA-3644-q5cj-c5c7 came from treating pulled manifests as executable config: a
    malicious one redirected model traffic and exfiltrated env vars.

    Identity is `fingerprint` (see keel/fingerprint.py); `sequence_number` exists only so
    humans can say "v3".
    """

    __tablename__ = "agent_versions"
    __table_args__ = (
        # Dedup enforced by the DATABASE, not just the handler: two concurrent identical
        # writes would otherwise both pass a handler-level check and insert twice.
        UniqueConstraint("agent_id", "fingerprint", name="uq_agent_versions_agent_fingerprint"),
        UniqueConstraint("agent_id", "sequence_number", name="uq_agent_versions_agent_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        # Carries its own tenant column even though it has an agent_id: RLS does NOT
        # inherit through a foreign key, so a child without its own policy is a leak.
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fingerprint_algo: Mapped[str] = mapped_column(String(10), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class AgentAlias(Base):
    """A mutable named pointer to one immutable version, e.g. `production`.

    Kept separate from `Agent.status` on purpose — status, deployment target and who may
    move the pointer are three orthogonal concerns (mlflow#10336).
    """

    __tablename__ = "agent_aliases"
    __table_args__ = (UniqueConstraint("agent_id", "name", name="uq_agent_aliases_agent_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class ApiKey(Base):
    """Machine credential. Only the SHA-256 hash is stored — never the key itself.

    Deliberately NOT under RLS: it is the credential table, looked up by an
    unguessable hash *before* the tenant context exists. Tenant data tables are
    the ones RLS protects (see migration 0001).
    """

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="default")
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Project(Base):
    """Tenant-scoped workspace. Protected by Row-Level Security in the database."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
