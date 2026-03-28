"""add organization, org_members, sso_configs, org_tenant_memberships tables

Revision ID: 0012
Revises: 0011
Create Date: 2026-03-28

Sprint 9: Organization SSO
- organizations: groups tenants under one billing/SSO unit
- organization_members: user membership in org with roles
- sso_configs: SAML/OIDC IdP configuration per org (Keycloak brokering)
- org_tenant_memberships: many-to-many between orgs and tenants
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "plan",
            sa.Enum("free", "starter", "pro", "enterprise", name="orgplan"),
            nullable=False,
            server_default="free",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("analytics_consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table(
        "organization_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "role",
            sa.Enum("owner", "admin", "member", "billing", name="orgmemberrole"),
            nullable=False,
            server_default="member",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organization_members_organization_id", "organization_members", ["organization_id"])
    op.create_index("ix_organization_members_user_id", "organization_members", ["user_id"])

    op.create_table(
        "sso_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "sso_type",
            sa.Enum("oidc", "saml", name="ssotype"),
            nullable=False,
        ),
        sa.Column("client_id", sa.String(length=512), nullable=True),
        sa.Column("client_secret", sa.String(length=512), nullable=True),
        sa.Column("discovery_url", sa.String(length=2048), nullable=True),
        sa.Column("metadata_url", sa.String(length=2048), nullable=True),
        sa.Column("metadata_xml", sa.Text(), nullable=True),
        sa.Column("keycloak_alias", sa.String(length=255), nullable=True),
        sa.Column("sso_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sso_configs_organization_id", "sso_configs", ["organization_id"])

    op.create_table(
        "org_tenant_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_tenant_memberships_organization_id", "org_tenant_memberships", ["organization_id"])
    op.create_index("ix_org_tenant_memberships_tenant_id", "org_tenant_memberships", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_org_tenant_memberships_tenant_id", table_name="org_tenant_memberships")
    op.drop_index("ix_org_tenant_memberships_organization_id", table_name="org_tenant_memberships")
    op.drop_table("org_tenant_memberships")
    op.drop_index("ix_sso_configs_organization_id", table_name="sso_configs")
    op.drop_table("sso_configs")
    op.drop_index("ix_organization_members_user_id", table_name="organization_members")
    op.drop_index("ix_organization_members_organization_id", table_name="organization_members")
    op.drop_table("organization_members")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
    op.execute("DROP TYPE IF EXISTS orgplan")
    op.execute("DROP TYPE IF EXISTS orgmemberrole")
    op.execute("DROP TYPE IF EXISTS ssotype")
