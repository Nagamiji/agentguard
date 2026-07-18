"""Read access to the tenant's audit trail and the RBAC role catalog."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from keel.deps import AdminOrg, DbSession, ReadOrg
from keel.models import AuditEvent
from keel.roles import ROLE_SCOPES
from keel.schemas import AuditEventOut

router = APIRouter(prefix="/v1", tags=["security"])


@router.get("/audit-events", response_model=list[AuditEventOut])
def list_audit_events(
    org_id: AdminOrg,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEventOut]:
    """Most-recent security-sensitive actions for the caller's org (admin only).

    RLS scopes the query to the caller's organization; no explicit org filter is needed.
    """
    rows = (
        db.execute(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit))
        .scalars()
        .all()
    )
    return [AuditEventOut.model_validate(r) for r in rows]


@router.get("/roles")
def list_roles(org_id: ReadOrg) -> dict[str, list[str]]:
    """The built-in RBAC roles and the scopes each expands to (keel/roles.py)."""
    return dict(ROLE_SCOPES)
