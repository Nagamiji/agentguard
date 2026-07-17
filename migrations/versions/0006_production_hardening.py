"""Phase 7: production hardening — scoped API keys and rate limits.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Add scopes to api_keys. Existing keys get '*' (all scopes).
    op.add_column(
        "api_keys",
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default='["*"]'),
    )
    # Add rate_limits to organizations. Default is empty dict (meaning system defaults).
    op.add_column(
        "organizations",
        sa.Column("rate_limits", postgresql.JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("organizations", "rate_limits")
    op.drop_column("api_keys", "scopes")
