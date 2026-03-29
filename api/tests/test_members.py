"""Tests for tenant member management endpoints."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def member_tenant(db_session: AsyncSession) -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="member-test",
        name="Member Test",
        namespace="tenant-member-test",
        keycloak_realm="member-test",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def owner_member(db_session: AsyncSession, member_tenant: Tenant) -> TenantMember:
    member = TenantMember(
        tenant_id=member_tenant.id,
        user_id="owner-001",
        email="owner@haven.nl",
        display_name="Owner",
        role=MemberRole.owner,
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


@pytest_asyncio.fixture
async def dev_member(db_session: AsyncSession, member_tenant: Tenant) -> TenantMember:
    member = TenantMember(
        tenant_id=member_tenant.id,
        user_id="dev-001",
        email="dev@haven.nl",
        display_name="Developer",
        role=MemberRole.member,
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


# ---------------------------------------------------------------------------
# List members
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_members_empty(async_client: AsyncClient, member_tenant: Tenant):
    resp = await async_client.get(f"/api/v1/tenants/{member_tenant.slug}/members")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_members(async_client: AsyncClient, member_tenant: Tenant, owner_member: TenantMember):
    resp = await async_client.get(f"/api/v1/tenants/{member_tenant.slug}/members")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["email"] == "owner@haven.nl"
    assert data[0]["role"] == "owner"


@pytest.mark.asyncio
async def test_list_members_tenant_not_found(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/tenants/nonexistent/members")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Add member
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_member(async_client: AsyncClient, member_tenant: Tenant):
    with patch("app.routers.members.keycloak_service") as mock_kc:
        mock_kc.create_user = AsyncMock(return_value="kc-user-123")
        resp = await async_client.post(
            f"/api/v1/tenants/{member_tenant.slug}/members",
            json={"email": "new@haven.nl", "display_name": "New User", "role": "member"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "new@haven.nl"
    assert data["display_name"] == "New User"
    assert data["role"] == "member"
    assert data["user_id"] == "kc-user-123"


@pytest.mark.asyncio
async def test_add_member_keycloak_fails_gracefully(async_client: AsyncClient, member_tenant: Tenant):
    """When Keycloak is down, member is still created with empty user_id."""
    with patch("app.routers.members.keycloak_service") as mock_kc:
        mock_kc.create_user = AsyncMock(side_effect=Exception("Keycloak unavailable"))
        resp = await async_client.post(
            f"/api/v1/tenants/{member_tenant.slug}/members",
            json={"email": "offline@haven.nl", "role": "viewer"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "offline@haven.nl"
    assert data["user_id"] == ""


@pytest.mark.asyncio
async def test_add_member_with_explicit_user_id(async_client: AsyncClient, member_tenant: Tenant):
    resp = await async_client.post(
        f"/api/v1/tenants/{member_tenant.slug}/members",
        json={"email": "explicit@haven.nl", "user_id": "explicit-id", "role": "admin"},
    )
    assert resp.status_code == 201
    assert resp.json()["user_id"] == "explicit-id"


@pytest.mark.asyncio
async def test_add_member_duplicate_email(
    async_client: AsyncClient, member_tenant: Tenant, owner_member: TenantMember
):
    with patch("app.routers.members.keycloak_service") as mock_kc:
        mock_kc.create_user = AsyncMock(return_value="kc-dup")
        resp = await async_client.post(
            f"/api/v1/tenants/{member_tenant.slug}/members",
            json={"email": "owner@haven.nl", "role": "member"},
        )
    assert resp.status_code == 409
    assert "already a member" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_add_member_tenant_not_found(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/tenants/nonexistent/members",
        json={"email": "no@haven.nl", "role": "viewer"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update member role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_member_role(
    async_client: AsyncClient, member_tenant: Tenant, dev_member: TenantMember
):
    resp = await async_client.patch(
        f"/api/v1/tenants/{member_tenant.slug}/members/{dev_member.user_id}",
        json={"role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_cannot_downgrade_last_owner(
    async_client: AsyncClient, member_tenant: Tenant, owner_member: TenantMember
):
    resp = await async_client.patch(
        f"/api/v1/tenants/{member_tenant.slug}/members/{owner_member.user_id}",
        json={"role": "member"},
    )
    assert resp.status_code == 409
    assert "at least one owner" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_can_downgrade_owner_when_multiple(
    async_client: AsyncClient, member_tenant: Tenant, owner_member: TenantMember, db_session: AsyncSession
):
    # Add a second owner
    second_owner = TenantMember(
        tenant_id=member_tenant.id,
        user_id="owner-002",
        email="owner2@haven.nl",
        role=MemberRole.owner,
    )
    db_session.add(second_owner)
    await db_session.commit()

    # Now we can downgrade the first owner
    resp = await async_client.patch(
        f"/api/v1/tenants/{member_tenant.slug}/members/{owner_member.user_id}",
        json={"role": "member"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "member"


@pytest.mark.asyncio
async def test_update_member_not_found(async_client: AsyncClient, member_tenant: Tenant):
    resp = await async_client.patch(
        f"/api/v1/tenants/{member_tenant.slug}/members/nonexistent",
        json={"role": "viewer"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Remove member
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_member(
    async_client: AsyncClient, member_tenant: Tenant, dev_member: TenantMember
):
    resp = await async_client.delete(
        f"/api/v1/tenants/{member_tenant.slug}/members/{dev_member.user_id}"
    )
    assert resp.status_code == 204

    # Verify member is gone
    list_resp = await async_client.get(f"/api/v1/tenants/{member_tenant.slug}/members")
    emails = [m["email"] for m in list_resp.json()]
    assert "dev@haven.nl" not in emails


@pytest.mark.asyncio
async def test_cannot_remove_last_owner(
    async_client: AsyncClient, member_tenant: Tenant, owner_member: TenantMember
):
    resp = await async_client.delete(
        f"/api/v1/tenants/{member_tenant.slug}/members/{owner_member.user_id}"
    )
    assert resp.status_code == 409
    assert "last owner" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_remove_member_not_found(async_client: AsyncClient, member_tenant: Tenant):
    resp = await async_client.delete(
        f"/api/v1/tenants/{member_tenant.slug}/members/nonexistent"
    )
    assert resp.status_code == 404
