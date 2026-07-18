"""Phase 15: RBAC / scoped API keys — key lifecycle metadata + audit trail.

Adds role/expiry/usage/provenance columns to api_keys, and an RLS-protected audit_events
table recording security-sensitive actions (key + org lifecycle).

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. api_keys lifecycle metadata. api_keys is deliberately NOT under RLS (it is the
    # credential table, looked up before tenant context exists), so no policy here.
    op.add_column("api_keys", sa.Column("role", sa.String(20), nullable=True))
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_keys", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_keys", sa.Column("created_by", sa.String(200), nullable=True))

    # 2. Tenant-scoped audit trail.
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("action", sa.String(100), nullable=False, index=True),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(200), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # RLS: mirror the tenant_isolation policy every tenant table carries. current_setting
    # (..., true) is NULL when unset -> zero rows, so no org context fails closed.
    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_events FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON audit_events
        USING (organization_id = current_setting('app.current_org_id', true)::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)
        """
    )

    # ALTER DEFAULT PRIVILEGES (migration 0002) already grants the app role DML on tables
    # created by the migration owner, so this is belt-and-suspenders — matching 0007.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keel_app') THEN
            GRANT SELECT, INSERT ON audit_events TO keel_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_column("api_keys", "created_by")
    op.drop_column("api_keys", "last_used_at")
    op.drop_column("api_keys", "expires_at")
    op.drop_column("api_keys", "role")
