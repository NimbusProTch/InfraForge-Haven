"""add mysql and mongodb service types

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-27

Adds 'mysql' and 'mongodb' to the servicetype enum for Percona Everest support.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL supports ALTER TYPE ... ADD VALUE for enums
    op.execute("ALTER TYPE servicetype ADD VALUE IF NOT EXISTS 'mysql'")
    op.execute("ALTER TYPE servicetype ADD VALUE IF NOT EXISTS 'mongodb'")


def downgrade() -> None:
    # Removing enum values requires recreating the type (complex, skip for now)
    pass
