"""add environments table and environment_id to deployments

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-28

Adds:
- environments table (staging / PR preview environments per application)
- environment_id nullable FK on deployments
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "environments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column(
            "env_type",
            sa.Enum("production", "staging", "preview", name="environmenttype"),
            nullable=False,
        ),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "building", "running", "failed", "deleting", name="environmentstatus"),
            nullable=False,
        ),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("env_vars", sa.JSON(), nullable=False),
        sa.Column("replicas", sa.Integer(), nullable=True),
        sa.Column("domain", sa.String(length=512), nullable=True),
        sa.Column("namespace_override", sa.String(length=63), nullable=True),
        sa.Column("last_image_tag", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_environments_application_id", "environments", ["application_id"])
    op.create_index("ix_environments_name", "environments", ["name"])

    # Add environment_id to deployments (nullable FK)
    op.add_column("deployments", sa.Column("environment_id", sa.Uuid(), nullable=True))
    op.create_index("ix_deployments_environment_id", "deployments", ["environment_id"])
    op.create_foreign_key(
        "fk_deployments_environment_id",
        "deployments",
        "environments",
        ["environment_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_deployments_environment_id", "deployments", type_="foreignkey")
    op.drop_index("ix_deployments_environment_id", table_name="deployments")
    op.drop_column("deployments", "environment_id")

    op.drop_index("ix_environments_name", table_name="environments")
    op.drop_index("ix_environments_application_id", table_name="environments")
    op.drop_table("environments")
    op.execute("DROP TYPE IF EXISTS environmenttype")
    op.execute("DROP TYPE IF EXISTS environmentstatus")
