"""add GDPR compliance models (user_consents, data_retention_policies)

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-28

Sprint 8: GDPR/AVG Compliance
- user_consents: tracks consent grants/revocations per user per tenant (Art. 7)
- data_retention_policies: configurable retention periods per tenant (Art. 5(1)(e))
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "consent_type",
            sa.Enum(
                "data_processing",
                "marketing",
                "analytics",
                "third_party_sharing",
                "data_retention",
                name="consenttype",
            ),
            nullable=False,
        ),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_consents_tenant_id", "user_consents", ["tenant_id"])
    op.create_index("ix_user_consents_user_id", "user_consents", ["user_id"])
    op.create_index("ix_user_consents_consent_type", "user_consents", ["consent_type"])

    op.create_table(
        "data_retention_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("audit_log_days", sa.Integer(), nullable=False, server_default="365"),
        sa.Column("deployment_log_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("build_log_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("usage_record_days", sa.Integer(), nullable=False, server_default="730"),
        sa.Column("inactive_app_days", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("policy_version", sa.String(length=20), nullable=False, server_default="1.0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_index("ix_data_retention_policies_tenant_id", "data_retention_policies", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_data_retention_policies_tenant_id", table_name="data_retention_policies")
    op.drop_table("data_retention_policies")
    op.drop_index("ix_user_consents_consent_type", table_name="user_consents")
    op.drop_index("ix_user_consents_user_id", table_name="user_consents")
    op.drop_index("ix_user_consents_tenant_id", table_name="user_consents")
    op.drop_table("user_consents")
    op.execute("DROP TYPE IF EXISTS consenttype")
