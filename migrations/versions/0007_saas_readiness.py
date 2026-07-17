"""Phase 10: SaaS customer readiness - plans, usage tracking, and onboarding.

Revision ID: 0007
Revises: 0006
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create plans table
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("scan_limit", sa.Integer(), nullable=False),
        sa.Column("agent_limit", sa.Integer(), nullable=False),
        sa.Column("features", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Seed default plans
    free_id = uuid.UUID("d781b2a9-7fbf-412d-9494-d02f5a04f32a")
    pilot_id = uuid.UUID("b7d41334-08fa-4a6c-9be2-4a0d8e8749a0")
    enterprise_id = uuid.UUID("e23bb410-61b6-4552-a5e2-7634f19b22cb")

    op.execute(
        sa.text(
            "INSERT INTO plans (id, name, scan_limit, agent_limit, features, created_at) "
            "VALUES "
            "(:free_id, 'free', 10, 1, '{}', NOW() AT TIME ZONE 'UTC'), "
            "(:pilot_id, 'pilot', 100, 5, '{\"advanced_scenarios\": true}', "
            "NOW() AT TIME ZONE 'UTC'), "
            "(:enterprise_id, 'enterprise', -1, -1, "
            '\'{"advanced_scenarios": true, "sso": true}\', '
            "NOW() AT TIME ZONE 'UTC')"
        ).bindparams(
            free_id=free_id,
            pilot_id=pilot_id,
            enterprise_id=enterprise_id,
        )
    )

    # 2. Add plan_id to organizations referencing plans.id
    op.add_column(
        "organizations",
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Default existing organizations to 'free' plan
    op.execute(
        sa.text("UPDATE organizations SET plan_id = :free_id WHERE plan_id IS NULL").bindparams(
            free_id=free_id
        )
    )

    # 3. Create usage_events table
    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
    )

    # 4. Enable Row-Level Security for usage_events
    op.execute("ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE usage_events FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON usage_events
        USING (organization_id = current_setting('app.current_org_id', true)::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org_id', true)::uuid)
        """
    )

    # 5. Grant permissions to keel_app
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keel_app') THEN
            GRANT SELECT ON plans TO keel_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON usage_events TO keel_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON usage_events")
    op.drop_table("usage_events")
    op.drop_column("organizations", "plan_id")
    op.drop_table("plans")
