"""Recording security-sensitive actions to the tenant-scoped audit trail.

Kept deliberately small: one write helper, called from the handlers that mutate keys or
org lifecycle. The write rides on the acting request's transaction (so it commits atomically
with the action) but never raises — an audit-log failure must not turn a successful
revoke into a 500.
"""

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from keel.models import AuditEvent

logger = logging.getLogger("keel.audit")


def record_audit_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor: str | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append an audit event within the current transaction. Best-effort; never raises.

    The row is added but NOT committed here — the calling handler commits it together with
    the action it describes, so the two succeed or fail as a unit. RLS requires the request's
    org context (set in keel/deps.py) to already be bound, which it always is for an
    authenticated handler. `actor` comes from `request.state.actor` (the acting key prefix).
    `request_id` is read from the request contextvar so callers need not thread it through;
    it is NULL for audit writes with no request context (background jobs / CLI).
    """
    from keel.context import get_request_id

    try:
        db.add(
            AuditEvent(
                organization_id=organization_id,
                actor=actor or "unknown",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                request_id=get_request_id(),
                event_metadata=metadata or {},
            )
        )
        db.flush()
    except Exception:  # pragma: no cover - audit must never break the primary action
        logger.warning("failed to record audit event action=%s", action, exc_info=True)
