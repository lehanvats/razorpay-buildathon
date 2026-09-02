"""case demo_loose_prompt flag

Revision ID: c40a5c800c5e
Revises: 14485460df78
Create Date: 2026-09-02 14:05:10.452426
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c40a5c800c5e"
down_revision: str | None = "14485460df78"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default=false so a NOT NULL add doesn't fail against a table
    # that already has rows (dev/Neon, not just the empty test DB).
    op.add_column(
        "cases",
        sa.Column("demo_loose_prompt", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("cases", "demo_loose_prompt")
