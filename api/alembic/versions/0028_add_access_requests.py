"""add access_requests table (enterprise onboarding funnel)

Backs the public /auth/request-access form. Anonymous INSERT (rate-limited
+ honeypot at router level), platform_admin SELECT/UPDATE. Flip status
to approved/rejected from the admin console. See
api/app/models/access_request.py for the full lifecycle.

Revision ID: 0028
Revises: 0027
Create Date: 2026-04-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_requests",
        sa.Column("id", sa.CHAR(32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("org_name", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="accessrequeststatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("submitter_ip", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_access_requests_email",
        "access_requests",
        ["email"],
        unique=False,
    )
    op.create_index(
        "ix_access_requests_status",
        "access_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_access_requests_status_created",
        "access_requests",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_access_requests_status_created", table_name="access_requests")
    op.drop_index("ix_access_requests_status", table_name="access_requests")
    op.drop_index("ix_access_requests_email", table_name="access_requests")
    op.drop_table("access_requests")
    # SQLAlchemy + Postgres: drop the enum type explicitly so down-migrate
    # can be re-upgraded cleanly.
    sa.Enum(name="accessrequeststatus").drop(op.get_bind(), checkfirst=True)
