"""add canary fields, app_type, volumes to applications; add cronjobs table

Revision ID: 0013
Revises: 0012
Create Date: 2026-03-28

Sprint 10 + Sprint 11:
- applications.app_type: web | worker | cronjob
- applications.canary_enabled, canary_weight
- applications.volumes: JSON array of persistent volume specs
- cronjobs table: K8s CronJob management
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add new columns to applications
    op.add_column(
        "applications",
        sa.Column(
            "app_type",
            sa.Enum("web", "worker", "cronjob", name="apptype"),
            nullable=False,
            server_default="web",
        ),
    )
    op.add_column(
        "applications",
        sa.Column("canary_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "applications",
        sa.Column("canary_weight", sa.Integer(), nullable=False, server_default="10"),
    )
    op.add_column(
        "applications",
        sa.Column("volumes", sa.JSON(), nullable=True),
    )

    # Create cronjobs table
    op.create_table(
        "cronjobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("schedule", sa.String(length=100), nullable=False),
        sa.Column("command", sa.JSON(), nullable=True),
        sa.Column("cpu_request", sa.String(length=32), nullable=False, server_default="50m"),
        sa.Column("cpu_limit", sa.String(length=32), nullable=False, server_default="500m"),
        sa.Column("memory_request", sa.String(length=32), nullable=False, server_default="64Mi"),
        sa.Column("memory_limit", sa.String(length=32), nullable=False, server_default="256Mi"),
        sa.Column("concurrency_policy", sa.String(length=32), nullable=False, server_default="Forbid"),
        sa.Column("successful_jobs_history", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("failed_jobs_history", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("starting_deadline_seconds", sa.Integer(), nullable=True),
        sa.Column("suspended", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("k8s_name", sa.String(length=255), nullable=True),
        sa.Column("last_schedule", sa.String(length=64), nullable=True),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("env_vars", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cronjobs_application_id", "cronjobs", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_cronjobs_application_id", table_name="cronjobs")
    op.drop_table("cronjobs")
    op.drop_column("applications", "volumes")
    op.drop_column("applications", "canary_weight")
    op.drop_column("applications", "canary_enabled")
    op.drop_column("applications", "app_type")
    op.execute("DROP TYPE IF EXISTS apptype")
