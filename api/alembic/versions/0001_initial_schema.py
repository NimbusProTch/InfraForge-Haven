"""initial schema: tenants, applications, deployments, build_jobs

Revision ID: 0001
Revises:
Create Date: 2026-03-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("namespace", sa.String(length=63), nullable=False),
        sa.Column("keycloak_realm", sa.String(length=255), nullable=False),
        sa.Column("cpu_limit", sa.String(length=20), nullable=False),
        sa.Column("memory_limit", sa.String(length=20), nullable=False),
        sa.Column("storage_limit", sa.String(length=20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)
    op.create_index("ix_tenants_namespace", "tenants", ["namespace"], unique=True)

    op.create_table(
        "applications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("repo_url", sa.String(length=512), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("env_vars", sa.JSON(), nullable=True),
        sa.Column("image_tag", sa.String(length=512), nullable=True),
        sa.Column("replicas", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_applications_tenant_id", "applications", ["tenant_id"])
    op.create_index("ix_applications_slug", "applications", ["slug"])

    op.create_table(
        "deployments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "building", "deploying", "running", "failed", name="deploymentstatus"),
            nullable=False,
        ),
        sa.Column("build_job_name", sa.String(length=255), nullable=True),
        sa.Column("image_tag", sa.String(length=512), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deployments_application_id", "deployments", ["application_id"])

    op.create_table(
        "build_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("deployment_id", sa.UUID(), nullable=False),
        sa.Column("k8s_job_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("logs", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_build_jobs_deployment_id", "build_jobs", ["deployment_id"])


def downgrade() -> None:
    op.drop_index("ix_build_jobs_deployment_id", table_name="build_jobs")
    op.drop_table("build_jobs")
    op.drop_index("ix_deployments_application_id", table_name="deployments")
    op.drop_table("deployments")
    op.execute("DROP TYPE IF EXISTS deploymentstatus")
    op.drop_index("ix_applications_slug", table_name="applications")
    op.drop_index("ix_applications_tenant_id", table_name="applications")
    op.drop_table("applications")
    op.drop_index("ix_tenants_namespace", table_name="tenants")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
