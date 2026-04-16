"""Regression test for Alembic migration 0016 duplicate tenant_members.

Migration 0016 originally created tenant_members (duplicate of 0007),
breaking `alembic upgrade head` on every fresh database with
`DuplicateTableError`. Recovery sprint 2026-04-17 removed the duplicate.
"""

from pathlib import Path


def test_0016_does_not_create_tenant_members() -> None:
    """Migration 0016 must NOT create tenant_members (0007 owns it)."""
    mig = Path(__file__).parent.parent / "alembic" / "versions" / "0016_add_missing_tables.py"
    text = mig.read_text()
    # Only one create_table call expected in 0016 (domain_verifications)
    assert text.count("op.create_table(") == 1, (
        "0016 should only create domain_verifications; tenant_members is owned by 0007"
    )
    # And it should NOT mention tenant_members as a create_table target
    # (mentions inside comments/docstrings are fine)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "op.create_table" in line:
            # Next few lines list the table name — verify it's not tenant_members
            table_line = lines[i + 1] if i + 1 < len(lines) else ""
            assert '"tenant_members"' not in table_line, (
                f"op.create_table target is tenant_members at line {i + 1}"
            )


def test_0016_downgrade_does_not_drop_tenant_members() -> None:
    """Migration 0016 downgrade should not drop tenant_members (0007 owns it)."""
    mig = Path(__file__).parent.parent / "alembic" / "versions" / "0016_add_missing_tables.py"
    text = mig.read_text()
    assert 'op.drop_table("tenant_members")' not in text, (
        "0016 downgrade should leave tenant_members to 0007's downgrade"
    )
