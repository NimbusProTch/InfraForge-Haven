"""add token_revocations table for Sprint H2 P9 / H2 #24

When a tenant member is removed (members.py::remove_member), insert/update
a row here to bump the user's reauth watermark. The JWT verifier reads
this on every request and rejects tokens with `iat < force_reauth_after`.

Revision ID: 0023
Revises: 0022
Create Date: 2026-04-09

Note: renumbered from 0022 to 0023 during rebase because 0022 was taken
by `0022_drop_build_jobs_table.py` (PR #80) which landed on main first.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "token_revocations",
        sa.Column("id", sa.CHAR(32), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("force_reauth_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_token_revocations_user_id"),
    )
    op.create_index(
        "ix_token_revocations_user_id",
        "token_revocations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_token_revocations_force_reauth_after_v2",
        "token_revocations",
        ["force_reauth_after"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_token_revocations_force_reauth_after_v2", table_name="token_revocations")
    op.drop_index("ix_token_revocations_user_id", table_name="token_revocations")
    op.drop_table("token_revocations")
