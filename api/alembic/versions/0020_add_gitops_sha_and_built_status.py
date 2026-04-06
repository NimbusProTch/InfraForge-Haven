"""Add gitops_commit_sha column and BUILT status to deployments.

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-06
"""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add gitops_commit_sha column (nullable)
    op.add_column("deployments", sa.Column("gitops_commit_sha", sa.String(255), nullable=True))

    # Add index on deployment status for faster queries
    op.create_index("ix_deployments_status", "deployments", ["status"])

    # Add 'built' value to deployment status enum
    # PostgreSQL requires explicit ALTER TYPE for enum
    op.execute("ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'built' AFTER 'building'")


def downgrade() -> None:
    op.drop_index("ix_deployments_status", table_name="deployments")
    op.drop_column("deployments", "gitops_commit_sha")
    # Note: PostgreSQL does not support removing enum values
