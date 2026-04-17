"""Test migration 0027 — add the 4 missing managed_services columns.

Regression guard: on 2026-04-18 a `POST /api/v1/tenants/{slug}/services`
returned HTTP 500 with asyncpg `UndefinedColumnError: column
managed_services.error_message does not exist`. Local SQLite tests did not
catch this because SQLite uses `Base.metadata.create_all()` (model-to-schema
— migrations bypassed), while prod Postgres is alembic-managed.

Covers two things:
1. Migration 0027 contains the 4 missing columns (error_message, db_name,
   db_user, credentials_provisioned) + `updating` enum value.
2. The ManagedService model's columns are all reachable through the migration
   chain (rough model↔migration drift check).
"""

from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent / "alembic" / "versions"
MIGRATION_FILE = MIGRATIONS_DIR / "0027_add_missing_managed_service_columns.py"


def test_0027_exists() -> None:
    assert MIGRATION_FILE.exists(), f"migration 0027 missing: {MIGRATION_FILE}"


def test_0027_adds_four_columns() -> None:
    """Migration 0027 MUST add error_message, db_name, db_user, credentials_provisioned."""
    text = MIGRATION_FILE.read_text()
    required = ["error_message", "db_name", "db_user", "credentials_provisioned"]
    for col in required:
        assert f'"{col}"' in text, f"migration 0027 does not add column {col!r}"


def test_0027_adds_updating_enum_value() -> None:
    """Migration 0027 MUST extend servicestatus with 'updating'."""
    text = MIGRATION_FILE.read_text()
    assert "ALTER TYPE servicestatus ADD VALUE IF NOT EXISTS 'updating'" in text, (
        "missing UPDATING enum extension — PATCH transitions will fail"
    )


def test_0027_adds_applications_port() -> None:
    """Migration 0027 MUST add applications.port (model default 8000)."""
    text = MIGRATION_FILE.read_text()
    assert "applications ADD COLUMN IF NOT EXISTS port" in text, (
        "missing applications.port — model has it but DB didn't, caused 2026-04-18 500"
    )


def test_model_fields_all_covered_by_migrations() -> None:
    """Every ManagedService + Application model column MUST appear in some migration.

    Catches future drift — if a new field lands on the model without a matching
    migration, this test fails immediately instead of waiting for prod 500s.
    """
    from app.models.application import Application
    from app.models.managed_service import ManagedService

    all_migrations_text = "\n".join(p.read_text() for p in MIGRATIONS_DIR.glob("*.py"))

    for model_cls, label in [(ManagedService, "managed_services"), (Application, "applications")]:
        column_names = [c.name for c in model_cls.__table__.columns]
        for col in column_names:
            # Look for column name as quoted string in any migration.
            # Matches both SQLAlchemy-op and raw SQL migration styles.
            assert (
                f'"{col}"' in all_migrations_text
                or f"'{col}'" in all_migrations_text
                or f" {col} " in all_migrations_text
            ), f"{label}.{col} has no migration — schema drift will 500 on prod Postgres"
