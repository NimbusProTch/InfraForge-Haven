"""Tests for the enterprise access-request funnel (ET1).

Covers:
- Anonymous POST with rate limit + honeypot
- Pydantic validation (disposable email blocklist, control chars)
- Platform-admin GET list + filter
- Platform-admin PATCH approve/reject
- Non-admin 403 on list/patch
- 409 when reviewing an already-reviewed request
"""

from __future__ import annotations

import uuid

import pytest

from app.deps import PLATFORM_ADMIN_ROLE, _is_platform_admin
from app.models.access_request import AccessRequest, AccessRequestStatus


class TestPlatformAdminGuard:
    """Unit tests for the _is_platform_admin helper.

    Kept separate from the endpoint tests so we can guard the logic
    without needing async_client plumbing.
    """

    def test_missing_realm_access_rejected(self):
        assert _is_platform_admin({}) is False

    def test_missing_roles_rejected(self):
        assert _is_platform_admin({"realm_access": {}}) is False

    def test_role_absent_rejected(self):
        assert _is_platform_admin({"realm_access": {"roles": ["something-else"]}}) is False

    def test_role_present_accepted(self):
        assert _is_platform_admin({"realm_access": {"roles": [PLATFORM_ADMIN_ROLE]}}) is True

    def test_ignores_resource_access(self):
        # Only realm-level role counts; client-scoped role is ignored.
        payload = {
            "realm_access": {"roles": ["default-roles-haven"]},
            "resource_access": {"iyziops-api": {"roles": [PLATFORM_ADMIN_ROLE]}},
        }
        assert _is_platform_admin(payload) is False

    def test_malformed_realm_access_rejected(self):
        assert _is_platform_admin({"realm_access": "not-a-dict"}) is False

    def test_malformed_roles_rejected(self):
        assert _is_platform_admin({"realm_access": {"roles": "not-a-list"}}) is False


# ---------------------------------------------------------------------------
# Anonymous POST /access-requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_access_request_returns_generic_thanks(async_client):
    """Successful submit returns a minimal body — no id, no timing."""
    resp = await async_client.post(
        "/api/v1/access-requests",
        json={
            "name": "Jan de Vries",
            "email": "jan@rotterdam.nl",
            "org_name": "Gemeente Rotterdam",
            "message": "We'd like to evaluate iyziops for our team.",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    # Minimal by design: no id (no enumeration), no created_at timing
    assert body == {"status": "received"}


@pytest.mark.asyncio
async def test_submit_access_request_persists_row(async_client, db_session):
    from sqlalchemy import select

    resp = await async_client.post(
        "/api/v1/access-requests",
        json={
            "name": "Marta Kowalski",
            "email": "marta@amsterdam.nl",
            "org_name": "Gemeente Amsterdam",
        },
    )
    assert resp.status_code == 201

    rows = (
        (await db_session.execute(select(AccessRequest).where(AccessRequest.email == "marta@amsterdam.nl")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    ar = rows[0]
    assert ar.status == AccessRequestStatus.PENDING
    assert ar.org_name == "Gemeente Amsterdam"
    assert ar.reviewed_by is None
    assert ar.message is None


@pytest.mark.asyncio
async def test_submit_access_request_honeypot_silently_ignored(async_client, db_session):
    """Bot fills the hidden 'website' field → we 201 but persist nothing.
    Goal: prevent bots from getting a retune signal (avoid 4xx response)."""
    from sqlalchemy import select

    resp = await async_client.post(
        "/api/v1/access-requests",
        json={
            "name": "Bot McBot",
            "email": "bot@example.com",
            "org_name": "BotCorp",
            "website": "https://spam.example.com",  # honeypot
        },
    )
    assert resp.status_code == 201
    rows = (
        (await db_session.execute(select(AccessRequest).where(AccessRequest.email == "bot@example.com")))
        .scalars()
        .all()
    )
    assert rows == []


@pytest.mark.asyncio
async def test_submit_access_request_rejects_disposable_email(async_client):
    resp = await async_client.post(
        "/api/v1/access-requests",
        json={
            "name": "Spammer",
            "email": "foo@mailinator.com",
            "org_name": "Throwaway Inc",
        },
    )
    assert resp.status_code == 422
    # Error mentions the validation rule — useful for the UI tooltip
    body = resp.json()
    assert "work email" in str(body).lower()


@pytest.mark.asyncio
async def test_submit_access_request_rejects_malformed_email(async_client):
    resp = await async_client.post(
        "/api/v1/access-requests",
        json={"name": "No Email", "email": "not-an-email", "org_name": "Acme"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_access_request_rejects_short_name(async_client):
    resp = await async_client.post(
        "/api/v1/access-requests",
        json={"name": "x", "email": "ok@example.com", "org_name": "Acme"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_access_request_rejects_control_chars(async_client):
    resp = await async_client.post(
        "/api/v1/access-requests",
        json={
            "name": "Bad\x00Name",
            "email": "ok@example.com",
            "org_name": "Acme",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Platform-admin GET /access-requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_requires_platform_admin(async_client):
    """A user WITHOUT the platform-admin role gets 403.

    The global conftest grants the role to the default user (so existing
    POST /tenants tests pass after the ET4 role-gate). Override here.
    """
    from app.auth.jwt import verify_token_not_revoked
    from app.main import app

    app.dependency_overrides[verify_token_not_revoked] = lambda: {
        "sub": "plain-user",
        "email": "plain@example.com",
        "realm_access": {"roles": ["default-roles-haven"]},
    }
    try:
        resp = await async_client.get("/api/v1/access-requests")
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)
    assert resp.status_code == 403
    assert "platform-admin" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_returns_all_for_admin(async_client, db_session):
    from app.auth.jwt import verify_token_not_revoked
    from app.main import app

    # Seed two rows
    db_session.add(
        AccessRequest(name="First", email="a@example.com", org_name="A Corp", status=AccessRequestStatus.PENDING)
    )
    db_session.add(
        AccessRequest(name="Second", email="b@example.com", org_name="B Corp", status=AccessRequestStatus.APPROVED)
    )
    await db_session.commit()

    # Override the verify_token dep for THIS test only
    def _admin_user():
        return {
            "sub": "admin-user",
            "email": "admin@iyziops.com",
            "realm_access": {"roles": [PLATFORM_ADMIN_ROLE]},
        }

    app.dependency_overrides[verify_token_not_revoked] = _admin_user
    try:
        resp = await async_client.get("/api/v1/access-requests")
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)

    assert resp.status_code == 200
    rows = resp.json()
    emails = {r["email"] for r in rows}
    assert "a@example.com" in emails
    assert "b@example.com" in emails


@pytest.mark.asyncio
async def test_list_filters_by_status(async_client, db_session):
    from app.auth.jwt import verify_token_not_revoked
    from app.main import app

    db_session.add(
        AccessRequest(name="Pending1", email="p1@ex.com", org_name="P Corp", status=AccessRequestStatus.PENDING)
    )
    db_session.add(
        AccessRequest(name="Approved1", email="a1@ex.com", org_name="A Corp", status=AccessRequestStatus.APPROVED)
    )
    await db_session.commit()

    app.dependency_overrides[verify_token_not_revoked] = lambda: {
        "sub": "admin",
        "realm_access": {"roles": [PLATFORM_ADMIN_ROLE]},
    }
    try:
        resp = await async_client.get("/api/v1/access-requests?status=approved")
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)

    assert resp.status_code == 200
    rows = resp.json()
    # Should NOT contain the pending row
    emails = {r["email"] for r in rows}
    assert "a1@ex.com" in emails
    assert "p1@ex.com" not in emails


# ---------------------------------------------------------------------------
# PATCH review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_requires_platform_admin(async_client, db_session):
    from app.auth.jwt import verify_token_not_revoked
    from app.main import app

    ar = AccessRequest(name="X", email="x@ex.com", org_name="X Corp", status=AccessRequestStatus.PENDING)
    db_session.add(ar)
    await db_session.commit()
    await db_session.refresh(ar)

    app.dependency_overrides[verify_token_not_revoked] = lambda: {
        "sub": "plain-user",
        "email": "plain@example.com",
        "realm_access": {"roles": ["default-roles-haven"]},
    }
    try:
        resp = await async_client.patch(
            f"/api/v1/access-requests/{ar.id}",
            json={"status": "approved"},
        )
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_approves_pending(async_client, db_session):
    from app.auth.jwt import verify_token_not_revoked
    from app.main import app

    ar = AccessRequest(name="X", email="x@ex.com", org_name="X Corp", status=AccessRequestStatus.PENDING)
    db_session.add(ar)
    await db_session.commit()
    await db_session.refresh(ar)

    app.dependency_overrides[verify_token_not_revoked] = lambda: {
        "sub": "admin-123",
        "realm_access": {"roles": [PLATFORM_ADMIN_ROLE]},
    }
    try:
        resp = await async_client.patch(
            f"/api/v1/access-requests/{ar.id}",
            json={"status": "approved", "review_notes": "looks legit"},
        )
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == "admin-123"
    assert body["reviewed_at"] is not None
    assert body["review_notes"] == "looks legit"


@pytest.mark.asyncio
async def test_patch_rejects_already_reviewed(async_client, db_session):
    from app.auth.jwt import verify_token_not_revoked
    from app.main import app

    ar = AccessRequest(name="X", email="x@ex.com", org_name="X Corp", status=AccessRequestStatus.APPROVED)
    db_session.add(ar)
    await db_session.commit()
    await db_session.refresh(ar)

    app.dependency_overrides[verify_token_not_revoked] = lambda: {
        "sub": "admin-123",
        "realm_access": {"roles": [PLATFORM_ADMIN_ROLE]},
    }
    try:
        resp = await async_client.patch(
            f"/api/v1/access-requests/{ar.id}",
            json={"status": "rejected"},
        )
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_patch_rejects_pending_status(async_client, db_session):
    """Reviewer can't flip back to pending — must be a terminal state."""
    from app.auth.jwt import verify_token_not_revoked
    from app.main import app

    ar = AccessRequest(name="X", email="x@ex.com", org_name="X Corp", status=AccessRequestStatus.PENDING)
    db_session.add(ar)
    await db_session.commit()
    await db_session.refresh(ar)

    app.dependency_overrides[verify_token_not_revoked] = lambda: {
        "sub": "admin",
        "realm_access": {"roles": [PLATFORM_ADMIN_ROLE]},
    }
    try:
        resp = await async_client.patch(
            f"/api/v1/access-requests/{ar.id}",
            json={"status": "pending"},
        )
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_unknown_id_returns_404(async_client):
    from app.auth.jwt import verify_token_not_revoked
    from app.main import app

    app.dependency_overrides[verify_token_not_revoked] = lambda: {
        "sub": "admin",
        "realm_access": {"roles": [PLATFORM_ADMIN_ROLE]},
    }
    try:
        resp = await async_client.patch(
            f"/api/v1/access-requests/{uuid.uuid4()}",
            json={"status": "approved"},
        )
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)

    assert resp.status_code == 404
