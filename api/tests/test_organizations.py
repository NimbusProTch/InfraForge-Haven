"""Tests for Organization CRUD + RBAC enforcement.

Covers:
- Organization CRUD with ownership auto-assignment
- RBAC: owner/admin/member/outsider access control
- Member management: invite, role change, last-owner protection
- Tenant binding: add/remove/duplicate
- Billing: role-based access
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db
from app.main import app
from app.models.organization import Organization, OrganizationMember, OrgMemberRole

# ---------------------------------------------------------------------------
# Test users
# ---------------------------------------------------------------------------

USER_OWNER = {"sub": "user-owner-001", "email": "owner@test.nl", "name": "Owner"}
USER_ADMIN = {"sub": "user-admin-002", "email": "admin@test.nl", "name": "Admin"}
USER_MEMBER = {"sub": "user-member-003", "email": "member@test.nl", "name": "Member"}
USER_OUTSIDER = {"sub": "user-outsider-999", "email": "outsider@test.nl", "name": "Outsider"}
PREFIX = "/api/v1/organizations"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _client_as(db_session: AsyncSession, user: dict) -> AsyncClient:
    """Create a test client authenticated as a specific user."""

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[verify_token] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def owner_client(db_session: AsyncSession):
    async with _client_as(db_session, USER_OWNER) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def org_with_members(db_session: AsyncSession) -> Organization:
    """Create an org with owner, admin, and member."""
    org = Organization(slug="test-org", name="Test Org")
    db_session.add(org)
    await db_session.flush()

    for user, role in [
        (USER_OWNER, OrgMemberRole.owner),
        (USER_ADMIN, OrgMemberRole.admin),
        (USER_MEMBER, OrgMemberRole.member),
    ]:
        db_session.add(
            OrganizationMember(
                organization_id=org.id,
                user_id=user["sub"],
                email=user["email"],
                display_name=user["name"],
                role=role,
            )
        )

    await db_session.commit()
    await db_session.refresh(org)
    return org


# ---------------------------------------------------------------------------
# Organization CRUD
# ---------------------------------------------------------------------------


class TestOrganizationCRUD:
    async def test_create_org_auto_adds_owner(self, owner_client: AsyncClient):
        resp = await owner_client.post(PREFIX, json={"slug": "new-org", "name": "New Org"})
        assert resp.status_code == 201
        assert resp.json()["slug"] == "new-org"

        # Creator is auto-added as owner
        members = await owner_client.get(f"{PREFIX}/new-org/members")
        assert members.status_code == 200
        assert len(members.json()) == 1
        assert members.json()[0]["role"] == "owner"
        assert members.json()[0]["email"] == USER_OWNER["email"]

    async def test_create_duplicate_slug_409(self, owner_client: AsyncClient, org_with_members: Organization):
        resp = await owner_client.post(PREFIX, json={"slug": "test-org", "name": "Duplicate"})
        assert resp.status_code == 409

    async def test_create_reserved_slug_422(self, owner_client: AsyncClient):
        resp = await owner_client.post(PREFIX, json={"slug": "admin", "name": "Admin Org"})
        assert resp.status_code == 422

    async def test_list_orgs_only_member_of(self, db_session: AsyncSession, org_with_members: Organization):
        # Owner sees the org
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.get(PREFIX)
            assert resp.status_code == 200
            assert len(resp.json()) == 1
            assert resp.json()[0]["slug"] == "test-org"

        # Outsider sees nothing
        async with _client_as(db_session, USER_OUTSIDER) as client:
            resp = await client.get(PREFIX)
            assert resp.status_code == 200
            assert len(resp.json()) == 0

    async def test_get_org_member_ok(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_MEMBER) as client:
            resp = await client.get(f"{PREFIX}/test-org")
            assert resp.status_code == 200
            assert resp.json()["slug"] == "test-org"

    async def test_get_org_outsider_403(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OUTSIDER) as client:
            resp = await client.get(f"{PREFIX}/test-org")
            assert resp.status_code == 403

    async def test_update_org_admin_ok(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_ADMIN) as client:
            resp = await client.patch(f"{PREFIX}/test-org", json={"name": "Updated"})
            assert resp.status_code == 200
            assert resp.json()["name"] == "Updated"

    async def test_update_org_member_403(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_MEMBER) as client:
            resp = await client.patch(f"{PREFIX}/test-org", json={"name": "Nope"})
            assert resp.status_code == 403

    async def test_delete_org_admin_403(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_ADMIN) as client:
            resp = await client.delete(f"{PREFIX}/test-org")
            assert resp.status_code == 403

    async def test_delete_org_owner_ok(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.delete(f"{PREFIX}/test-org")
            assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Member Management
# ---------------------------------------------------------------------------


class TestMemberManagement:
    async def test_list_members_member_ok(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_MEMBER) as client:
            resp = await client.get(f"{PREFIX}/test-org/members")
            assert resp.status_code == 200
            assert len(resp.json()) == 3

    async def test_list_members_outsider_403(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OUTSIDER) as client:
            resp = await client.get(f"{PREFIX}/test-org/members")
            assert resp.status_code == 403

    async def test_invite_member_admin_ok(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_ADMIN) as client:
            resp = await client.post(
                f"{PREFIX}/test-org/members",
                json={"user_id": "new-user-004", "email": "new@test.nl", "role": "member"},
            )
            assert resp.status_code == 201

    async def test_invite_member_member_403(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_MEMBER) as client:
            resp = await client.post(
                f"{PREFIX}/test-org/members",
                json={"user_id": "new-user-005", "email": "nope@test.nl", "role": "member"},
            )
            assert resp.status_code == 403

    async def test_invite_duplicate_409(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.post(
                f"{PREFIX}/test-org/members",
                json={"user_id": USER_MEMBER["sub"], "email": USER_MEMBER["email"], "role": "member"},
            )
            assert resp.status_code == 409

    async def test_update_role(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.patch(
                f"{PREFIX}/test-org/members/{USER_MEMBER['sub']}",
                json={"role": "admin"},
            )
            assert resp.status_code == 200
            assert resp.json()["role"] == "admin"

    async def test_cannot_demote_last_owner(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.patch(
                f"{PREFIX}/test-org/members/{USER_OWNER['sub']}",
                json={"role": "member"},
            )
            assert resp.status_code == 400
            assert "last owner" in resp.json()["detail"]

    async def test_cannot_remove_last_owner(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.delete(f"{PREFIX}/test-org/members/{USER_OWNER['sub']}")
            assert resp.status_code == 400

    async def test_remove_member_ok(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.delete(f"{PREFIX}/test-org/members/{USER_MEMBER['sub']}")
            assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Tenant Binding
# ---------------------------------------------------------------------------


class TestTenantBinding:
    async def test_bind_tenant_admin_ok(self, db_session: AsyncSession, org_with_members: Organization):
        tid = str(uuid.uuid4())
        async with _client_as(db_session, USER_ADMIN) as client:
            resp = await client.post(f"{PREFIX}/test-org/tenants", json={"tenant_id": tid})
            assert resp.status_code == 201

    async def test_bind_tenant_member_403(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_MEMBER) as client:
            resp = await client.post(f"{PREFIX}/test-org/tenants", json={"tenant_id": str(uuid.uuid4())})
            assert resp.status_code == 403

    async def test_bind_duplicate_409(self, db_session: AsyncSession, org_with_members: Organization):
        tid = str(uuid.uuid4())
        async with _client_as(db_session, USER_OWNER) as client:
            await client.post(f"{PREFIX}/test-org/tenants", json={"tenant_id": tid})
            resp = await client.post(f"{PREFIX}/test-org/tenants", json={"tenant_id": tid})
            assert resp.status_code == 409

    async def test_list_tenants_member_ok(self, db_session: AsyncSession, org_with_members: Organization):
        tid = str(uuid.uuid4())
        async with _client_as(db_session, USER_OWNER) as client:
            await client.post(f"{PREFIX}/test-org/tenants", json={"tenant_id": tid})
        async with _client_as(db_session, USER_MEMBER) as client:
            resp = await client.get(f"{PREFIX}/test-org/tenants")
            assert resp.status_code == 200
            assert len(resp.json()) == 1

    async def test_list_tenants_outsider_403(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OUTSIDER) as client:
            resp = await client.get(f"{PREFIX}/test-org/tenants")
            assert resp.status_code == 403

    async def test_unbind_tenant(self, db_session: AsyncSession, org_with_members: Organization):
        tid = str(uuid.uuid4())
        async with _client_as(db_session, USER_OWNER) as client:
            await client.post(f"{PREFIX}/test-org/tenants", json={"tenant_id": tid})
            resp = await client.delete(f"{PREFIX}/test-org/tenants/{tid}")
            assert resp.status_code == 204


# ---------------------------------------------------------------------------
# SSO Config
# ---------------------------------------------------------------------------


class TestSSOConfig:
    async def test_create_oidc_owner_ok(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.post(
                f"{PREFIX}/test-org/sso",
                json={
                    "sso_type": "oidc",
                    "client_id": "haven",
                    "client_secret": "secret",
                    "discovery_url": "https://sso.test.nl/.well-known/openid-configuration",
                },
            )
            assert resp.status_code == 201
            assert resp.json()["sso_type"] == "oidc"

    async def test_create_oidc_missing_discovery_400(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.post(
                f"{PREFIX}/test-org/sso",
                json={"sso_type": "oidc", "client_id": "haven"},
            )
            assert resp.status_code == 400

    async def test_create_saml_ok(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.post(
                f"{PREFIX}/test-org/sso",
                json={"sso_type": "saml", "metadata_url": "https://sso.test.nl/saml/metadata"},
            )
            assert resp.status_code == 201

    async def test_sso_admin_can_list(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_ADMIN) as client:
            resp = await client.get(f"{PREFIX}/test-org/sso")
            assert resp.status_code == 200

    async def test_sso_member_403(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_MEMBER) as client:
            resp = await client.get(f"{PREFIX}/test-org/sso")
            assert resp.status_code == 403

    async def test_sso_admin_cannot_create(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_ADMIN) as client:
            resp = await client.post(
                f"{PREFIX}/test-org/sso",
                json={"sso_type": "oidc", "client_id": "x", "discovery_url": "https://x.nl/.well-known/oidc"},
            )
            assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------


class TestBilling:
    async def test_billing_owner_ok(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_OWNER) as client:
            resp = await client.get(f"{PREFIX}/test-org/billing")
            assert resp.status_code == 200
            assert resp.json()["plan"] == "free"
            assert resp.json()["tenant_count"] == 0

    async def test_billing_admin_ok(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_ADMIN) as client:
            resp = await client.get(f"{PREFIX}/test-org/billing")
            assert resp.status_code == 200

    async def test_billing_member_403(self, db_session: AsyncSession, org_with_members: Organization):
        async with _client_as(db_session, USER_MEMBER) as client:
            resp = await client.get(f"{PREFIX}/test-org/billing")
            assert resp.status_code == 403
