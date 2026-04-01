"""Add compound unique constraints to prevent race conditions.

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-01
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Application slug must be unique within a tenant
    op.create_unique_constraint("uq_app_tenant_slug", "applications", ["tenant_id", "slug"])

    # Managed service name must be unique within a tenant
    op.create_unique_constraint("uq_svc_tenant_name", "managed_services", ["tenant_id", "name"])

    # Environment name must be unique within an application
    op.create_unique_constraint("uq_env_app_name", "environments", ["application_id", "name"])

    # Org-tenant membership must be unique
    op.create_unique_constraint("uq_org_tenant", "org_tenant_memberships", ["organization_id", "tenant_id"])


def downgrade() -> None:
    op.drop_constraint("uq_org_tenant", "org_tenant_memberships", type_="unique")
    op.drop_constraint("uq_env_app_name", "environments", type_="unique")
    op.drop_constraint("uq_svc_tenant_name", "managed_services", type_="unique")
    op.drop_constraint("uq_app_tenant_slug", "applications", type_="unique")
