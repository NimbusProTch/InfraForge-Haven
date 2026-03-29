"""add monorepo and dependency detection fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-26

Adds dockerfile_path, build_context, detected_deps, use_dockerfile to applications.
Adds custom_domain, health_check_path, resource_cpu_request, resource_cpu_limit,
resource_memory_request, resource_memory_limit, min_replicas, max_replicas,
cpu_threshold to applications for Sprint 6.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Sprint 3: Monorepo support
    op.add_column("applications", sa.Column("dockerfile_path", sa.String(512), nullable=True))
    op.add_column("applications", sa.Column("build_context", sa.String(512), nullable=True))
    op.add_column("applications", sa.Column("use_dockerfile", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("applications", sa.Column("detected_deps", sa.JSON(), nullable=True))

    # Sprint 6: Production hardening
    op.add_column("applications", sa.Column("custom_domain", sa.String(255), nullable=True))
    op.add_column("applications", sa.Column("health_check_path", sa.String(512), nullable=True))
    op.add_column(
        "applications", sa.Column("resource_cpu_request", sa.String(32), server_default="50m", nullable=False)
    )  # noqa: E501
    op.add_column("applications", sa.Column("resource_cpu_limit", sa.String(32), server_default="500m", nullable=False))
    op.add_column(
        "applications", sa.Column("resource_memory_request", sa.String(32), server_default="64Mi", nullable=False)
    )  # noqa: E501
    op.add_column(
        "applications", sa.Column("resource_memory_limit", sa.String(32), server_default="512Mi", nullable=False)
    )  # noqa: E501
    op.add_column("applications", sa.Column("min_replicas", sa.Integer(), server_default="1", nullable=False))
    op.add_column("applications", sa.Column("max_replicas", sa.Integer(), server_default="5", nullable=False))
    op.add_column("applications", sa.Column("cpu_threshold", sa.Integer(), server_default="70", nullable=False))
    op.add_column("applications", sa.Column("auto_deploy", sa.Boolean(), server_default="true", nullable=False))


def downgrade() -> None:
    op.drop_column("applications", "auto_deploy")
    op.drop_column("applications", "cpu_threshold")
    op.drop_column("applications", "max_replicas")
    op.drop_column("applications", "min_replicas")
    op.drop_column("applications", "resource_memory_limit")
    op.drop_column("applications", "resource_memory_request")
    op.drop_column("applications", "resource_cpu_limit")
    op.drop_column("applications", "resource_cpu_request")
    op.drop_column("applications", "health_check_path")
    op.drop_column("applications", "custom_domain")
    op.drop_column("applications", "detected_deps")
    op.drop_column("applications", "use_dockerfile")
    op.drop_column("applications", "build_context")
    op.drop_column("applications", "dockerfile_path")
