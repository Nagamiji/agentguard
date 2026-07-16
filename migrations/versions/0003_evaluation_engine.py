"""EVAL-01: evaluation engine — scenarios, runs, results.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Each carries its own organization_id and policy: RLS does not inherit through a foreign
# key, so a child without its own policy is a cross-tenant leak even when its parent is
# protected. eval_results is the sharpest case — it holds agent outputs, which is the most
# sensitive data in the product.
TENANT_TABLES = ("eval_scenarios", "eval_runs", "eval_results")


def upgrade() -> None:
    op.create_table(
        "eval_scenarios",
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
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("input", postgresql.JSONB(), nullable=False),
        sa.Column("checks", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "slug", name="uq_eval_scenarios_agent_slug"),
    )

    op.create_table(
        "eval_runs",
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
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_versions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Denormalised: the gate looks up a verdict BY fingerprint.
        sa.Column("fingerprint", sa.String(64), nullable=False, index=True),
        sa.Column("runner", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("gate_decision", sa.String(20), nullable=False),
        sa.Column("total_scenarios", sa.Integer(), nullable=False),
        sa.Column("failed_scenarios", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('passed', 'failed', 'errored')", name="ck_eval_runs_status"),
        sa.CheckConstraint(
            "gate_decision IN ('allowed', 'blocked', 'unknown')",
            name="ck_eval_runs_gate_decision",
        ),
    )

    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "scenario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_scenarios.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("failures", postgresql.JSONB(), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # The gate's hot path: "latest verdict for this agent + fingerprint".
    op.create_index(
        "ix_eval_runs_agent_fingerprint_created",
        "eval_runs",
        ["agent_id", "fingerprint", "created_at"],
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

    # 0002 registered ALTER DEFAULT PRIVILEGES, so the tables above are already granted to
    # keel_app automatically. The explicit grant stays as a belt-and-braces no-op: it costs
    # nothing and it keeps this migration correct if it is ever replayed against a database
    # where the default privileges were not registered.
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
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_index("ix_eval_runs_agent_fingerprint_created", table_name="eval_runs")
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
    op.drop_table("eval_scenarios")
