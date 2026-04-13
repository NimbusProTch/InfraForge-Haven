"""Regression test for Alembic migration 0025: rename servicetype enum 'postgresql' → 'postgres'.

The migration must:
1. Import cleanly (no syntax errors).
2. Have correct `revision` and `down_revision` chaining to 0024.
3. Contain an IF EXISTS guard so fresh DBs (where 'postgres' is already the label)
   are a no-op rather than erroring.
4. Issue `ALTER TYPE servicetype RENAME VALUE 'postgresql' TO 'postgres'` on match.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MIGRATION_FILE = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0025_rename_servicetype_postgresql_to_postgres.py"
)


@pytest.fixture(scope="module")
def migration_module():
    assert MIGRATION_FILE.exists(), f"Migration file missing: {MIGRATION_FILE}"
    spec = importlib.util.spec_from_file_location("migration_0025", MIGRATION_FILE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_revision_chain(migration_module):
    assert migration_module.revision == "0025"
    assert migration_module.down_revision == "0024"


def test_upgrade_function_exists(migration_module):
    assert hasattr(migration_module, "upgrade")
    assert callable(migration_module.upgrade)
    assert hasattr(migration_module, "downgrade")


def test_migration_body_is_conditional_rename(migration_module):
    """The SQL body must be idempotent: only rename if 'postgresql' label exists."""
    body = MIGRATION_FILE.read_text()
    # Must check for the label before renaming (idempotent on fresh DB)
    assert "SELECT 1" in body
    assert "pg_enum" in body
    assert "pg_type" in body
    assert "'postgresql'" in body
    assert "typname = 'servicetype'" in body
    # Must do the rename inside the IF-EXISTS guard
    assert "ALTER TYPE servicetype RENAME VALUE 'postgresql' TO 'postgres'" in body
    # Wrapped in a DO block so the IF-EXISTS check runs as procedural SQL
    assert "DO $$" in body
    assert "END $$;" in body
