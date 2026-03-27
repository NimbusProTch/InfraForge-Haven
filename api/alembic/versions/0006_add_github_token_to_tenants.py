"""add github_token to tenants

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-28

Adds github_token column to tenants table for private repo access.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("github_token", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "github_token")
