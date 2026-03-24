"""add managed_services table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "managed_services",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column(
            "service_type",
            sa.Enum("postgres", "redis", "rabbitmq", name="servicetype"),
            nullable=False,
        ),
        sa.Column(
            "tier",
            sa.Enum("dev", "prod", name="servicetier"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("provisioning", "ready", "failed", "deleting", name="servicestatus"),
            nullable=False,
        ),
        sa.Column("secret_name", sa.String(length=255), nullable=True),
        sa.Column("service_namespace", sa.String(length=63), nullable=True),
        sa.Column("connection_hint", sa.String(length=512), nullable=True),
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
    op.create_index("ix_managed_services_tenant_id", "managed_services", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_managed_services_tenant_id", table_name="managed_services")
    op.drop_table("managed_services")
    op.execute("DROP TYPE IF EXISTS servicestatus")
    op.execute("DROP TYPE IF EXISTS servicetier")
    op.execute("DROP TYPE IF EXISTS servicetype")
