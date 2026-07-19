"""Observability Phase 1: correlate audit events with HTTP logs.

Adds a nullable, indexed `request_id` to audit_events so a stored audit row can be joined
to the structured HTTP log line for the same request. Additive and nullable: existing rows
keep NULL, and audit writes with no request context (background jobs / CLI) stay NULL.
No RLS change — the table-level policy and GRANTs from 0009 already cover new columns.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("request_id", sa.String(64), nullable=True))
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_column("audit_events", "request_id")
