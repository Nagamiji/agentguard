"""BE-02: agent registry — agents, immutable versions, mutable aliases.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Every one of these carries its own organization_id and its own policy. RLS does NOT
# inherit through a foreign key: a child table without its own policy is a cross-tenant
# leak even when its parent is protected.
TENANT_TABLES = ("agents", "agent_versions", "agent_aliases")


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("framework", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "slug", name="uq_agents_org_slug"),
        # status is the record's lifecycle ONLY — never deployment state (mlflow#10336).
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_agents_status"),
    )

    op.create_table(
        "agent_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, index=True),
        sa.Column("fingerprint_algo", sa.String(10), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Dedup is a database guarantee, not a handler convention: two concurrent identical
        # writes would both pass a SELECT-then-INSERT check in the app.
        sa.UniqueConstraint("agent_id", "fingerprint", name="uq_agent_versions_agent_fingerprint"),
        sa.UniqueConstraint("agent_id", "sequence_number", name="uq_agent_versions_agent_seq"),
    )

    op.create_table(
        "agent_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            # RESTRICT, not CASCADE: a version that something points at must not vanish
            # silently — deleting it should be a loud error, not a dangling deployment.
            sa.ForeignKey("agent_versions.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "name", name="uq_agent_aliases_agent_name"),
    )

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # Defence in depth: the app connects as keel_app, which is not the owner, but FORCE
        # means the policy still applies if that ever changes.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # current_setting(..., true) returns NULL when unset -> comparison is NULL -> zero
        # rows. Fail-closed by construction: no tenant context, no data.
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (organization_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)
            """
        )

    # 0001's `GRANT ... ON ALL TABLES` was evaluated once, at that migration's execution
    # time — it is a snapshot, not a standing rule, so it does NOT cover the tables above.
    # Without the two statements below, every app query against them fails with
    # `permission denied` at RUNTIME (CI hides this: it migrates and tests in one pass).
    #
    # ALTER DEFAULT PRIVILEGES fixes the class of bug rather than this instance: any table a
    # FUTURE migration creates is granted automatically, so nobody has to remember. It is
    # scoped to the role that creates the tables (migrations run as the owner) and is not
    # retroactive — hence the explicit grant as well, for the tables created just above.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keel_app') THEN
            EXECUTE format(
              'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
              'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO keel_app',
              current_user
            );
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO keel_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keel_app') THEN
            EXECUTE format(
              'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
              'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM keel_app',
              current_user
            );
          END IF;
        END $$;
        """
    )
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("agent_aliases")
    op.drop_table("agent_versions")
    op.drop_table("agents")
