"""Add missing tables: domain_verifications.

Revision ID: 0016
Revises: 0015
Create Date: 2026-03-29

NOTE: The original 0016 also created `tenant_members`, duplicating migration
0007 (which already creates the same table). This caused `DuplicateTableError`
on every fresh-DB `alembic upgrade head` run, since tenant_members exists by
the time 0016 runs. The duplicate block was removed during the 2026-04-17
overnight recovery sprint. Migration 0007 remains the authoritative creator.
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domain_verifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id"), index=True, nullable=False),
        sa.Column("domain", sa.String(255), index=True, nullable=False),
        sa.Column("verification_token", sa.String(64), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "certificate_status",
            sa.Enum("pending", "issuing", "issued", "failed", name="certificatestatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("certificate_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("certificate_error", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    # 0007 owns tenant_members — don't drop it here, only domain_verifications.
    op.drop_table("domain_verifications")
