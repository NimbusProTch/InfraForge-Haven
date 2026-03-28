"""add billing tables (usage_records + tenant.tier)

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-28

Adds:
- usage_records table for per-period billing metrics
- tier column on tenants (free | starter | pro | enterprise)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add tier column to tenants
    op.add_column("tenants", sa.Column("tier", sa.String(length=20), nullable=False, server_default="free"))

    # Create usage_records table
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cpu_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("memory_gb_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("storage_gb_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("build_minutes", sa.Float(), nullable=False, server_default="0"),
        sa.Column("bandwidth_gb", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_records_tenant_id", "usage_records", ["tenant_id"])
    op.create_index("ix_usage_records_period_start", "usage_records", ["period_start"])


def downgrade() -> None:
    op.drop_index("ix_usage_records_period_start", table_name="usage_records")
    op.drop_index("ix_usage_records_tenant_id", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_column("tenants", "tier")
