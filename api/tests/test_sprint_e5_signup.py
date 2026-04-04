"""Tests for Sprint E5: Self-service signup + team member management.

Tests:
- /tenants/me returns user's tenants
- New user gets empty tenant list
- Keycloak service: enable_self_registration method
- Member invite + list + update role + remove
- Prevent last owner removal
- GitHub OAuth endpoints exist
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.main import app
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.services.keycloak_service import KeycloakService


async def _tenant(db: AsyncSession, slug: str = "signup-test") -> Tenant:
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


async def _member(
    db: AsyncSession, tenant: Tenant, user_id: str, email: str, role: MemberRole = MemberRole("member")
) -> TenantMember:
    m = TenantMember(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user_id,
        email=email,
        role=role,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


@pytest_asyncio.fixture
async def auth_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = False

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "user-123", "email": "user@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /tenants/me — user onboarding flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenants_me_empty_for_new_user(auth_client):
    """/tenants/me returns empty list for new user (no memberships)."""
    resp = await auth_client.get("/api/v1/tenants/me")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_tenants_me_returns_user_tenants(auth_client, db_session):
    """/tenants/me returns tenants the user is a member of."""
    t1 = await _tenant(db_session, "my-project-1")
    t2 = await _tenant(db_session, "my-project-2")
    await _member(db_session, t1, "user-123", "user@haven.nl", MemberRole("owner"))
    await _member(db_session, t2, "user-123", "user@haven.nl", MemberRole("member"))

    resp = await auth_client.get("/api/v1/tenants/me")
    assert resp.status_code == 200
    slugs = {t["slug"] for t in resp.json()}
    assert slugs == {"my-project-1", "my-project-2"}


@pytest.mark.asyncio
async def test_tenants_me_excludes_other_users(auth_client, db_session):
    """/tenants/me doesn't show tenants of other users."""
    t = await _tenant(db_session, "other-user-project")
    await _member(db_session, t, "other-user-456", "other@haven.nl")

    resp = await auth_client.get("/api/v1/tenants/me")
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Keycloak service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keycloak_enable_self_registration():
    """KeycloakService.enable_self_registration calls the correct API."""
    kc = KeycloakService()
    with patch.object(kc, "_get_admin_token", return_value="mock-token"):
        with patch("httpx.AsyncClient.put") as mock_put:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_put.return_value = mock_resp
            await kc.enable_self_registration("haven")
            mock_put.assert_called_once()
            call_args = mock_put.call_args
            assert "haven" in call_args.args[0]
            assert call_args.kwargs["json"]["registrationAllowed"] is True


def test_keycloak_service_has_create_user():
    """KeycloakService has create_user method."""
    kc = KeycloakService()
    assert hasattr(kc, "create_user")
    assert callable(kc.create_user)


def test_keycloak_service_has_create_realm():
    """KeycloakService has create_realm method."""
    kc = KeycloakService()
    assert hasattr(kc, "create_realm")
    assert callable(kc.create_realm)


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_members(auth_client, db_session):
    """GET /members returns all members of a tenant."""
    t = await _tenant(db_session, "members-list")
    await _member(db_session, t, "user-123", "user@haven.nl", MemberRole("owner"))  # RBAC
    await _member(db_session, t, "user-1", "a@test.nl", MemberRole("owner"))
    await _member(db_session, t, "user-2", "b@test.nl", MemberRole("member"))

    resp = await auth_client.get(f"/api/v1/tenants/{t.slug}/members")
    assert resp.status_code == 200
    assert len(resp.json()) == 3  # user-123 (RBAC owner) + user-1 + user-2


@pytest.mark.asyncio
async def test_add_member(auth_client, db_session):
    """POST /members creates a new tenant member (requires owner/admin)."""
    t = await _tenant(db_session, "add-member")
    await _member(db_session, t, "user-123", "user@haven.nl", MemberRole("owner"))  # RBAC: caller is owner

    resp = await auth_client.post(
        f"/api/v1/tenants/{t.slug}/members",
        json={"email": "new@test.nl", "role": "member"},
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "new@test.nl"


@pytest.mark.asyncio
async def test_add_duplicate_member_409(auth_client, db_session):
    """POST /members with duplicate email returns 409."""
    t = await _tenant(db_session, "dup-member")
    await _member(db_session, t, "user-123", "user@haven.nl", MemberRole("owner"))  # RBAC
    await _member(db_session, t, "user-1", "exists@test.nl")

    resp = await auth_client.post(
        f"/api/v1/tenants/{t.slug}/members",
        json={"email": "exists@test.nl", "role": "member"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_member_role(auth_client, db_session):
    """PATCH /members/{user_id} updates role."""
    t = await _tenant(db_session, "update-role")
    m = await _member(db_session, t, "user-1", "user@test.nl", MemberRole("member"))

    resp = await auth_client.patch(
        f"/api/v1/tenants/{t.slug}/members/{m.user_id}",
        json={"role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_remove_member(auth_client, db_session):
    """DELETE /members/{user_id} removes member."""
    t = await _tenant(db_session, "remove-member")
    await _member(db_session, t, "owner-1", "owner@test.nl", MemberRole("owner"))
    m = await _member(db_session, t, "user-1", "user@test.nl", MemberRole("member"))

    resp = await auth_client.delete(f"/api/v1/tenants/{t.slug}/members/{m.user_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cannot_remove_last_owner(auth_client, db_session):
    """Cannot remove the last owner of a tenant."""
    t = await _tenant(db_session, "last-owner")
    m = await _member(db_session, t, "only-owner", "owner@test.nl", MemberRole("owner"))

    resp = await auth_client.delete(f"/api/v1/tenants/{t.slug}/members/{m.user_id}")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GitHub OAuth endpoints exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_callback_endpoint_exists(auth_client):
    """GitHub OAuth callback endpoint exists (may fail on validation, not 404)."""
    resp = await auth_client.get("/api/v1/github/auth/callback?code=test&state=test")
    assert resp.status_code != 404


def test_github_router_registered():
    """GitHub router is included in the app."""
    from app.routers import github

    assert hasattr(github, "router")
