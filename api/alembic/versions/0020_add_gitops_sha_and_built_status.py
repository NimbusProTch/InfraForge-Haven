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
    # Idempotent: use raw SQL with IF NOT EXISTS for DBs created via create_all()
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE deployments ADD COLUMN gitops_commit_sha VARCHAR(255);
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$;
    """)

    # Add index on deployment status (idempotent)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_deployments_status ON deployments (status);
    """)

    # Add 'built' value to deployment status enum (IF NOT EXISTS is PG 9.3+)
    op.execute("ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'built' AFTER 'building'")


def downgrade() -> None:
    op.drop_index("ix_deployments_status", table_name="deployments")
    op.drop_column("deployments", "gitops_commit_sha")
    # Note: PostgreSQL does not support removing enum values
