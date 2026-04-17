"""Add missing managed_services + applications columns + servicestatus.UPDATING.

Revision ID: 0027
Revises: 0026
Create Date: 2026-04-18

Model↔migration drift accumulated during Sprint A (Everest DB provisioning)
and Sprint 6 (production hardening). Several SQLAlchemy fields existed in
the model but had no migration adding them to the database:

  managed_services:
    - error_message (String 1024)    — set by provisioning/sync failures
    - db_name (String 63)            — custom DB name, used by connect-service
    - db_user (String 63)            — custom DB user, used by connect-service
    - credentials_provisioned (bool) — prevents re-provisioning same creds

  applications:
    - port (int default 8000)        — container port forwarded by the Service

  servicestatus enum:
    - updating                       — mid-flight PATCH state

The drift surfaced on 2026-04-18 during Everest GitOps sprint E2E:
  - `POST /api/v1/tenants/{slug}/services` → 500 `column managed_services.error_message does not exist`
  - `GET /api/v1/tenants/{slug}/services`  → 500 `column applications.port does not exist`

Local SQLite tests did not catch this because SQLite uses
`Base.metadata.create_all()` (model-to-schema, bypasses Alembic). Production
Postgres is alembic-managed exclusively.

The upgrade uses raw `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` SQL so the
migration is idempotent: safe to run even if the columns were added
out-of-band during incident recovery (as they were on dev 2026-04-18).
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- managed_services: 4 missing columns (idempotent) -----------------
    op.execute("ALTER TABLE managed_services ADD COLUMN IF NOT EXISTS error_message VARCHAR(1024)")
    op.execute("ALTER TABLE managed_services ADD COLUMN IF NOT EXISTS db_name VARCHAR(63)")
    op.execute("ALTER TABLE managed_services ADD COLUMN IF NOT EXISTS db_user VARCHAR(63)")
    op.execute(
        "ALTER TABLE managed_services ADD COLUMN IF NOT EXISTS credentials_provisioned BOOLEAN NOT NULL DEFAULT false"
    )

    # --- applications: port column (idempotent) ----------------------------
    op.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS port INTEGER NOT NULL DEFAULT 8000")

    # --- servicestatus enum: add 'updating' --------------------------------
    # `ADD VALUE IF NOT EXISTS` supported since Postgres 9.6; CNPG 17+ fine.
    op.execute("ALTER TYPE servicestatus ADD VALUE IF NOT EXISTS 'updating'")


def downgrade() -> None:
    # Postgres can't remove an enum value cleanly without recreating the type.
    # Since `updating` is additive and harmless if left behind, downgrade keeps
    # the enum value in place. Columns are dropped symmetrically.
    op.drop_column("applications", "port")
    op.drop_column("managed_services", "credentials_provisioned")
    op.drop_column("managed_services", "db_user")
    op.drop_column("managed_services", "db_name")
    op.drop_column("managed_services", "error_message")
