"""rename servicetype enum 'postgresql' to 'postgres' if present

Revision ID: 0025
Revises: 0024
Create Date: 2026-04-12

Idempotent repair: some live databases have the `servicetype` enum with the
label 'postgresql' (instead of 'postgres' as declared in migration 0002).
Root cause unclear — suspected manual ALTER TYPE or a transient code
checkout where ServiceType.POSTGRES had value 'postgresql'.

This migration renames 'postgresql' to 'postgres' IF AND ONLY IF that label
exists. On a fresh DB (migration 0002 already creates 'postgres'), this is
a no-op. On the broken DB, this fixes the mismatch between ``ServiceType``
Python enum values and the PostgreSQL enum labels, unblocking
`POST /tenants/{slug}/services` with `service_type=postgres`.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'servicetype'
                  AND e.enumlabel = 'postgresql'
            ) THEN
                ALTER TYPE servicetype RENAME VALUE 'postgresql' TO 'postgres';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Irreversible without recreating the enum type; not worth the complexity.
    pass
