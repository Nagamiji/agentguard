"""Phase 11: Organization lifecycle status column.

Adds a 'status' column to the organizations table to support
the pending / active / suspended / deleted lifecycle for beta customer management.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_VALID_STATUSES = ("pending", "active", "suspended", "deleted")


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
    )
    op.create_check_constraint(
        "ck_organizations_status",
        "organizations",
        sa.column("status").in_(_VALID_STATUSES),
    )
    op.create_index("ix_organizations_status", "organizations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_organizations_status", table_name="organizations")
    op.drop_constraint("ck_organizations_status", "organizations", type_="check")
    op.drop_column("organizations", "status")
