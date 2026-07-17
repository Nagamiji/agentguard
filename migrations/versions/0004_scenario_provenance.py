"""Phase 3: record where a scenario came from (custom vs the built-in library).

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # `source` distinguishes a customer's own scenario from one seeded from the library, so a
    # risk report can say "we tested you against v2026.07.1 of the corpus" and re-import can
    # skip what is already present. server_default keeps existing rows valid as 'custom'.
    op.add_column(
        "eval_scenarios",
        sa.Column("source", sa.String(20), nullable=False, server_default="custom"),
    )
    # Which library version seeded this row. NULL for custom scenarios.
    op.add_column("eval_scenarios", sa.Column("library_version", sa.String(20), nullable=True))

    # eval_scenarios already has its RLS policy (0003) and keel_app already holds DML on it
    # (0002's ALTER DEFAULT PRIVILEGES); adding columns needs no re-grant.


def downgrade() -> None:
    op.drop_column("eval_scenarios", "library_version")
    op.drop_column("eval_scenarios", "source")
