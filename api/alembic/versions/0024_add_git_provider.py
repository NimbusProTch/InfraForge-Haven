"""add git_provider column to applications

Sprint 3: Per-tenant internal git via Gitea. Applications can now
specify their source code provider (github or gitea).

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create the enum type first
    git_provider_enum = sa.Enum("github", "gitea", name="gitprovider")
    git_provider_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "applications",
        sa.Column("git_provider", git_provider_enum, server_default="github", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("applications", "git_provider")
    # Drop the enum type
    sa.Enum(name="gitprovider").drop(op.get_bind(), checkfirst=True)
