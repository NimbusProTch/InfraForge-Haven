"""Add pending_services JSON column to applications.

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-06
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("pending_services", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "pending_services")
