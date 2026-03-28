"""add clusters table + cluster_id to applications

Revision ID: 0014
Revises: 0013
Create Date: 2026-03-28

Sprint 12: Multi-cluster, Multi-region support.
- New `clusters` table with health, failover, and region fields.
- `applications.cluster_id` FK → nullable (existing apps use default cluster).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create clusters table
    op.create_table(
        "clusters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=False),
        sa.Column("region_label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column(
            "provider",
            sa.Enum(
                "hetzner", "cyso", "leafcloud", "aws", "azure", "gcp", "other",
                name="clusterprovider",
            ),
            nullable=False,
            server_default="hetzner",
        ),
        sa.Column("api_endpoint", sa.String(length=512), nullable=False),
        sa.Column("kubeconfig_secret", sa.String(length=255), nullable=True),
        sa.Column("kubeconfig_data", sa.String(length=65535), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "degraded", "unknown", name="clusterstatus"),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedulable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_message", sa.String(length=1024), nullable=True),
        sa.Column("node_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failover_cluster_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clusters_name", "clusters", ["name"], unique=True)
    op.create_index("ix_clusters_region", "clusters", ["region"])
    op.create_index("ix_clusters_status", "clusters", ["status"])

    # Add cluster_id FK to applications
    op.add_column(
        "applications",
        sa.Column("cluster_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_applications_cluster_id",
        "applications",
        "clusters",
        ["cluster_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_applications_cluster_id", "applications", ["cluster_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_cluster_id", table_name="applications")
    op.drop_constraint("fk_applications_cluster_id", "applications", type_="foreignkey")
    op.drop_column("applications", "cluster_id")

    op.drop_index("ix_clusters_status", table_name="clusters")
    op.drop_index("ix_clusters_region", table_name="clusters")
    op.drop_index("ix_clusters_name", table_name="clusters")
    op.drop_table("clusters")
    op.execute("DROP TYPE IF EXISTS clusterstatus")
    op.execute("DROP TYPE IF EXISTS clusterprovider")
