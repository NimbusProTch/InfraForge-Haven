"""Add env_from_secrets column to applications table.

Revision ID: 0015
Revises: 0014
Create Date: 2026-03-29
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("env_from_secrets", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "env_from_secrets")
