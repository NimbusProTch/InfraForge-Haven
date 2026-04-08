"""drop build_jobs table (H3b — model deleted in P2.2)

The build_jobs table has been unused since the build pipeline switched to
submitting K8s Jobs directly via the Kubernetes Python client. The
SQLAlchemy `BuildJob` model carried a `# TODO: Remove unused model` since
that switch and was deleted in Sprint H3 (P2.2). This migration drops the
table itself.

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-09
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The original 0001_initial_schema migration created build_jobs with a
    # foreign key to deployments and an index on deployment_id. Drop the
    # index first, then the table.
    #
    # Use IF EXISTS variants because some dev DBs may have been created via
    # `Base.metadata.create_all()` and skipped this index name (the test
    # SQLite session creates the table directly without going through the
    # named index).
    op.execute("DROP INDEX IF EXISTS ix_build_jobs_deployment_id")
    op.execute("DROP TABLE IF EXISTS build_jobs")


def downgrade() -> None:
    # Recreate the original schema if needed. Mirror of 0001_initial_schema's
    # build_jobs block.
    import sqlalchemy as sa

    op.create_table(
        "build_jobs",
        sa.Column("id", sa.CHAR(32), nullable=False),
        sa.Column("deployment_id", sa.CHAR(32), nullable=False),
        sa.Column("k8s_job_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("logs", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_build_jobs_deployment_id", "build_jobs", ["deployment_id"])
