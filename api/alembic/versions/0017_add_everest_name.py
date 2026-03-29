"""Add everest_name column to managed_services for tenant-prefixed DB names.

Revision ID: 0017
Revises: 0016
Create Date: 2026-03-29
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("managed_services", sa.Column("everest_name", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("managed_services", "everest_name")
