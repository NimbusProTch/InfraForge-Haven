"""Add degraded status to servicestatus enum.

Revision ID: 0018
Revises: 0017
Create Date: 2026-03-30
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE servicestatus ADD VALUE IF NOT EXISTS 'degraded'")


def downgrade() -> None:
    pass
