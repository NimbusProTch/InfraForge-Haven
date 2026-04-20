"""Tests for the token revocation list — Sprint H2 P9 / H2 #24.

Covers:
  - The service layer: revoke_user, is_token_revoked, cleanup_expired
  - The integration: removing a tenant member triggers a revocation row
  - The dependency: verify_token_not_revoked rejects pre-revocation tokens

The conftest.py default `async_client` fixture overrides
`verify_token_not_revoked` so existing tests don't hit the DB. The tests
in this file build their OWN client without that override, so the real
revocation lookup runs.
"""

import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.main import app
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.models.token_revocation import TokenRevocation
from app.services import token_revocation_service
from app.services.token_revocation_service import (
    cleanup_expired_revocations,
    is_token_revoked,
    revoke_user,
)


@pytest.fixture(autouse=True)
def _clear_revocation_cache():
    """Reset the in-process revocation cache between tests so cached
    "not revoked" results from one test don't leak into the next."""
    token_revocation_service._clear_cache_for_tests()
    yield
    token_revocation_service._clear_cache_for_tests()


# ---------------------------------------------------------------------------
# Service-layer tests (no HTTP, just the DB + cache)
# ---------------------------------------------------------------------------


def _to_naive(dt: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip; normalise both sides for comparison."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


@pytest.mark.asyncio
async def test_revoke_user_creates_row(db_session: AsyncSession):
    """First revoke creates a new row with NOW() as the watermark."""
    await revoke_user(db_session, user_id="user-a", reason="test")
    await db_session.commit()

    result = await db_session.execute(select(TokenRevocation).where(TokenRevocation.user_id == "user-a"))
    row = result.scalar_one()
    assert row.user_id == "user-a"
    assert row.reason == "test"
    delta = _to_naive(datetime.now(UTC)) - _to_naive(row.force_reauth_after)
    assert delta.total_seconds() < 5


@pytest.mark.asyncio
async def test_revoke_user_is_idempotent(db_session: AsyncSession):
    """Calling revoke_user twice updates the existing row, not duplicates."""
    await revoke_user(db_session, user_id="user-b", reason="first")
    await db_session.commit()
    first_time = (
        await db_session.execute(select(TokenRevocation.force_reauth_after).where(TokenRevocation.user_id == "user-b"))
    ).scalar_one()

    # Wait so the second watermark is strictly later
    import asyncio

    await asyncio.sleep(0.05)

    await revoke_user(db_session, user_id="user-b", reason="second")
    await db_session.commit()

    rows = (
        (await db_session.execute(select(TokenRevocation).where(TokenRevocation.user_id == "user-b"))).scalars().all()
    )
    assert len(rows) == 1
    assert rows[0].reason == "second"
    assert rows[0].force_reauth_after > first_time


@pytest.mark.asyncio
async def test_is_token_revoked_no_row_returns_false(db_session: AsyncSession):
    """A user with no revocation row is not revoked."""
    revoked = await is_token_revoked(db_session, user_id="never-revoked", token_iat_epoch=time.time())
    assert revoked is False


@pytest.mark.asyncio
async def test_is_token_revoked_iat_before_watermark_returns_true(db_session: AsyncSession):
    """A token issued BEFORE the watermark is rejected."""
    await revoke_user(db_session, user_id="user-c", reason="test")
    await db_session.commit()

    # Token was issued 1 hour ago — way before the just-now watermark
    old_iat = time.time() - 3600
    revoked = await is_token_revoked(db_session, user_id="user-c", token_iat_epoch=old_iat)
    assert revoked is True


@pytest.mark.asyncio
async def test_is_token_revoked_iat_after_watermark_returns_false(db_session: AsyncSession):
    """A token issued AFTER the watermark (re-login) is accepted."""
    await revoke_user(db_session, user_id="user-d", reason="test")
    await db_session.commit()

    # Token was issued 5 seconds AFTER the watermark
    fresh_iat = time.time() + 5
    revoked = await is_token_revoked(db_session, user_id="user-d", token_iat_epoch=fresh_iat)
    assert revoked is False


@pytest.mark.asyncio
async def test_is_token_revoked_missing_iat_returns_true(db_session: AsyncSession):
    """A token with no iat claim is malformed → reject."""
    revoked = await is_token_revoked(db_session, user_id="any-user", token_iat_epoch=None)
    assert revoked is True


@pytest.mark.asyncio
async def test_cleanup_removes_old_rows(db_session: AsyncSession):
    """Rows older than the retention window are deleted."""
    old_row = TokenRevocation(
        user_id="user-old",
        force_reauth_after=datetime.now(UTC) - timedelta(hours=48),
        reason="old",
    )
    fresh_row = TokenRevocation(
        user_id="user-fresh",
        force_reauth_after=datetime.now(UTC),
        reason="fresh",
    )
    db_session.add_all([old_row, fresh_row])
    await db_session.commit()

    deleted = await cleanup_expired_revocations(db_session)
    await db_session.commit()
    assert deleted == 1

    remaining = (await db_session.execute(select(TokenRevocation.user_id))).scalars().all()
    assert "user-fresh" in remaining
    assert "user-old" not in remaining


# ---------------------------------------------------------------------------
# HTTP integration: removing a member triggers revocation
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def member_setup(db_session: AsyncSession) -> tuple[Tenant, TenantMember]:
    """A tenant with the test-user as owner + a separate member to remove."""
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="rev-tenant",
        name="Revocation Test",
        namespace="tenant-rev-tenant",
        keycloak_realm="rev-tenant",
        cpu_limit="2",
        memory_limit="4Gi",
        storage_limit="20Gi",
    )
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(
        TenantMember(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            user_id="test-user",
            email="test@haven.nl",
            role=MemberRole("owner"),
        )
    )
    target = TenantMember(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id="member-to-remove",
        email="bye@example.com",
        role=MemberRole("member"),
    )
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(target)
    return tenant, target


@pytest.mark.asyncio
async def test_remove_member_inserts_revocation_row(
    async_client: AsyncClient,
    db_session: AsyncSession,
    member_setup: tuple[Tenant, TenantMember],
):
    """When `DELETE /members/{user_id}` succeeds, a TokenRevocation row
    appears for the removed user."""
    tenant, target = member_setup

    response = await async_client.delete(
        f"/api/v1/tenants/{tenant.slug}/members/{target.user_id}",
    )
    assert response.status_code == 204, response.text

    rows = (
        (await db_session.execute(select(TokenRevocation).where(TokenRevocation.user_id == target.user_id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.reason is not None
    assert tenant.slug in row.reason


# ---------------------------------------------------------------------------
# Dependency-level test: verify_token_not_revoked rejects revoked tokens
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def real_revocation_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """A client that does NOT override `verify_token_not_revoked` — the real
    DB lookup runs. Used for tests that need to assert the dependency
    behavior end-to-end.
    """
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = False

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {
        "sub": "verified-user",
        "email": "verified@example.com",
        "iat": int(time.time() - 60),  # token issued 1 minute ago
        "realm_access": {"roles": ["platform-admin"]},
    }
    # Deliberately do NOT override verify_token_not_revoked — let the
    # real wrapper hit the (in-memory SQLite) DB.

    # Patch the wrapper's _SessionLocal so it uses the test session
    # instead of the real engine. (The wrapper does
    # `from app.deps import _SessionLocal` lazily inside the function.)
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_session_local():
        yield db_session

    # NOTE: do NOT `import app.deps` here — that would shadow the
    # `app` (FastAPI instance) imported at the top of this module
    # within the fixture scope and trigger an UnboundLocalError.
    from app import deps as _deps_module

    original_factory = _deps_module._SessionLocal
    _deps_module._SessionLocal = _fake_session_local  # type: ignore[assignment]

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        _deps_module._SessionLocal = original_factory
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_verify_token_not_revoked_rejects_pre_revocation_token(
    real_revocation_client: AsyncClient,
    db_session: AsyncSession,
):
    """A token whose `iat` is BEFORE the user's revocation watermark
    must get 401 from the protected endpoint."""
    # Insert a fresh revocation row for the test user
    await revoke_user(db_session, user_id="verified-user", reason="test rejection")
    await db_session.commit()

    # Hit ANY protected endpoint — /tenants/me requires auth
    response = await real_revocation_client.get("/api/v1/tenants/me")
    assert response.status_code == 401, f"expected revoked → 401, got {response.status_code}: {response.text[:200]}"
    assert "revoked" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_verify_token_not_revoked_accepts_post_revocation_token(
    real_revocation_client: AsyncClient,
    db_session: AsyncSession,
):
    """A token whose `iat` is AFTER the user's revocation watermark
    (i.e. they re-authenticated) must succeed."""
    # Insert a revocation watermark in the PAST
    past_row = TokenRevocation(
        user_id="verified-user",
        force_reauth_after=datetime.now(UTC) - timedelta(hours=2),
        reason="old revocation",
    )
    db_session.add(past_row)
    await db_session.commit()

    # The mock token has iat = NOW - 60s, which is AFTER the 2h-old watermark
    response = await real_revocation_client.get("/api/v1/tenants/me")
    assert response.status_code == 200, f"expected post-revocation token → 200, got {response.status_code}"
