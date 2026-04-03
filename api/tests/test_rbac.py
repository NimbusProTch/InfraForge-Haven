"""Tests for RBAC enforcement (Sprint H1.1).

Tests role-based access control: require_role dependency, tenant membership,
role hierarchy, and forbidden access for non-members.
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.auth.rbac import require_role, require_tenant_member
from app.deps import get_db, get_k8s
from app.main import app
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember


async def _tenant(db: AsyncSession, slug: str = "rbac-test") -> Tenant:
    t = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        name=slug,
        namespace=f"tenant-{slug}",
        keycloak_realm=slug,
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def _member(db: AsyncSession, tenant: Tenant, user_id: str, role: str = "member") -> TenantMember:
    m = TenantMember(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user_id,
        email=f"{user_id}@test.nl",
        role=MemberRole(role),
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


def _client_factory(db_session, user_id="rbac-user"):
    """Create client with specific user_id."""
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = False

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": user_id, "email": f"{user_id}@test.nl"}

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def rbac_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async with _client_factory(db_session, "rbac-user") as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# RBAC module tests
# ---------------------------------------------------------------------------


def test_role_hierarchy():
    """MemberRole has all expected values."""
    assert MemberRole.owner.value == "owner"
    assert MemberRole.admin.value == "admin"
    assert MemberRole.member.value == "member"
    assert MemberRole.viewer.value == "viewer"


def test_require_role_returns_callable():
    """require_role returns a FastAPI dependency."""
    dep = require_role("admin")
    assert callable(dep)


def test_require_role_multiple_roles():
    """require_role accepts multiple role strings."""
    dep = require_role("owner", "admin")
    assert callable(dep)


# ---------------------------------------------------------------------------
# Members endpoint RBAC tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_member_requires_owner_or_admin(db_session):
    """POST /members requires owner or admin role (viewer gets 403)."""
    t = await _tenant(db_session, "rbac-add")
    await _member(db_session, t, "viewer-user", "viewer")

    async with _client_factory(db_session, "viewer-user") as client:
        resp = await client.post(
            f"/api/v1/tenants/{t.slug}/members",
            json={"email": "new@test.nl", "role": "member"},
        )
        assert resp.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_add_member_allowed_for_admin(db_session):
    """POST /members succeeds for admin role."""
    t = await _tenant(db_session, "rbac-admin")
    await _member(db_session, t, "admin-user", "admin")

    async with _client_factory(db_session, "admin-user") as client:
        resp = await client.post(
            f"/api/v1/tenants/{t.slug}/members",
            json={"email": "new@test.nl", "role": "member"},
        )
        assert resp.status_code == 201
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_add_member_allowed_for_owner(db_session):
    """POST /members succeeds for owner role."""
    t = await _tenant(db_session, "rbac-owner")
    await _member(db_session, t, "owner-user", "owner")

    async with _client_factory(db_session, "owner-user") as client:
        resp = await client.post(
            f"/api/v1/tenants/{t.slug}/members",
            json={"email": "new2@test.nl", "role": "member"},
        )
        assert resp.status_code == 201
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_non_member_gets_403(db_session):
    """POST /members by non-member returns 403."""
    t = await _tenant(db_session, "rbac-nonmember")
    # No membership for "stranger"

    async with _client_factory(db_session, "stranger") as client:
        resp = await client.post(
            f"/api/v1/tenants/{t.slug}/members",
            json={"email": "new@test.nl", "role": "member"},
        )
        assert resp.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_members_still_works(rbac_client, db_session):
    """GET /members works without RBAC (read access for all members)."""
    t = await _tenant(db_session, "rbac-list")
    await _member(db_session, t, "rbac-user", "member")

    resp = await rbac_client.get(f"/api/v1/tenants/{t.slug}/members")
    assert resp.status_code == 200
