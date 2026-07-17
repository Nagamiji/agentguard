"""Phase 4: policy engine — policies, immutable policy versions, and run-time audit.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Both carry their own organization_id + policy: RLS does not inherit through a foreign key.
TENANT_TABLES = ("policies", "policy_versions")


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # scope_type in (organization, project, agent); scope_id is the id of that thing.
        # (project scope is accepted by the schema but agents are not yet linked to projects,
        # so it does not resolve — see ADR 0012. Kept in the CHECK for forward compatibility.)
        sa.Column("scope_type", sa.String(20), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        # NULL environment = applies to every environment; a specific env overrides it.
        sa.Column("environment", sa.String(30), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope_type IN ('organization', 'project', 'agent')", name="ck_policies_scope_type"
        ),
        # One policy per (scope, environment). NULLs are distinct in a UNIQUE index in
        # Postgres, so an env-agnostic policy and an env-specific one can coexist — which is
        # exactly what the resolver layers.
        sa.UniqueConstraint(
            "organization_id",
            "scope_type",
            "scope_id",
            "environment",
            name="uq_policies_scope_env",
        ),
    )

    op.create_table(
        "policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Append-only audit history: a version is never updated. Dedup + ordering enforced
        # by the database, not just the handler.
        sa.UniqueConstraint("policy_id", "fingerprint", name="uq_policy_versions_fingerprint"),
        sa.UniqueConstraint("policy_id", "sequence_number", name="uq_policy_versions_seq"),
    )

    # Audit on the run: which environment it ran for, which effective policy it enforced
    # (by fingerprint), and any static policy violations found. Nullable — runs predating a
    # policy simply have none.
    op.add_column("eval_runs", sa.Column("environment", sa.String(30), nullable=True))
    op.add_column("eval_runs", sa.Column("policy_fingerprint", sa.String(64), nullable=True))
    op.add_column(
        "eval_runs",
        sa.Column("policy_findings", postgresql.JSONB(), nullable=False, server_default="[]"),
    )

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (organization_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)
            """
        )

    # 0002's ALTER DEFAULT PRIVILEGES already grants keel_app on these new tables; the
    # explicit grant is a belt-and-braces no-op kept for replay safety.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keel_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO keel_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_column("eval_runs", "policy_findings")
    op.drop_column("eval_runs", "policy_fingerprint")
    op.drop_column("eval_runs", "environment")
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("policy_versions")
    op.drop_table("policies")
