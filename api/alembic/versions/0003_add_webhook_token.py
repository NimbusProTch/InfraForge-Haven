"""add webhook_token to applications

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-24

Adds the webhook_token column to the applications table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("webhook_token", sa.String(64), nullable=True),
    )
    # Populate existing rows with unique tokens
    op.execute(
        "UPDATE applications "
        "SET webhook_token = replace(gen_random_uuid()::text, '-', '') "
        "                 || replace(gen_random_uuid()::text, '-', '') "
        "WHERE webhook_token IS NULL"
    )
    op.alter_column("applications", "webhook_token", nullable=False)
    op.create_unique_constraint("uq_applications_webhook_token", "applications", ["webhook_token"])
    op.create_index("ix_applications_webhook_token", "applications", ["webhook_token"])


def downgrade() -> None:
    op.drop_index("ix_applications_webhook_token", table_name="applications")
    op.drop_constraint("uq_applications_webhook_token", "applications", type_="unique")
    op.drop_column("applications", "webhook_token")
