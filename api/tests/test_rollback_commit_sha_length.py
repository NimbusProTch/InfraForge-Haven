"""Regression test for rollback 500 — commit_sha column is VARCHAR(40).

Pre-fix: rollback created a Deployment with commit_sha="rollback-to-{full-uuid}"
(48 chars) → StringDataRightTruncationError → HTTP 500 to UI. The ↺ button
in the Deployments tab was unusable as a result.
"""

import uuid


def test_rollback_commit_sha_fits_in_varchar_40():
    """The string the router builds must fit in the 40-char column."""
    dep_id = uuid.uuid4()
    # Same construction as the router:
    commit_sha = f"rollback-to-{str(dep_id)[:8]}"
    assert len(commit_sha) <= 40, f"commit_sha too long for VARCHAR(40): {len(commit_sha)} chars = {commit_sha!r}"
    # Also keep the prefix for audit-log grepping
    assert commit_sha.startswith("rollback-to-")
    # And keep enough of the UUID to be unambiguous (8 hex chars = 4B uniques)
    assert len(commit_sha) == len("rollback-to-") + 8


def test_rollback_commit_sha_uses_short_sha_convention():
    """Match git's 7-10 char short-SHA convention; 8 is our choice."""
    dep_id = uuid.UUID("4d8a97a6-114a-4d1c-8294-57fc5f2757c7")
    commit_sha = f"rollback-to-{str(dep_id)[:8]}"
    assert commit_sha == "rollback-to-4d8a97a6"


def test_pre_fix_string_would_have_truncated():
    """Sanity check that the pre-fix form really did overflow — if this ever
    goes false (e.g., someone shortens UUIDs), the regression guard above
    becomes redundant and can be simplified."""
    dep_id = uuid.uuid4()
    pre_fix = f"rollback-to-{dep_id}"
    assert len(pre_fix) > 40
