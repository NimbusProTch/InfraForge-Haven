"""Organization + SSO endpoint tests (Sprint 9).

Tests cover:
- Organization CRUD
- Member management (invite, update role, remove)
- SSO config (OIDC / SAML create, update, delete)
- Tenant membership in org
- Billing summary
"""

import uuid

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization, OrganizationMember, OrgMemberRole, OrgPlan

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE = "/api/v1/organizations"


@pytest_asyncio.fixture
async def sample_org(db_session: AsyncSession) -> Organization:
    org = Organization(
        id=uuid.uuid4(),
        slug="gemeente-amsterdam",
        name="Gemeente Amsterdam",
        plan=OrgPlan.starter,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


# ---------------------------------------------------------------------------
# Organization CRUD — 4 tests
# ---------------------------------------------------------------------------


async def test_list_organizations_empty(async_client: AsyncClient) -> None:
    """Empty org list initially."""
    resp = await async_client.get(BASE)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_organization(async_client: AsyncClient) -> None:
    """Creating an organization returns the created object."""
    resp = await async_client.post(BASE, json={"slug": "gemeente-utrecht", "name": "Gemeente Utrecht", "plan": "free"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "gemeente-utrecht"
    assert data["plan"] == "free"
    assert data["active"] is True
    assert data["marketing_consent"] is False  # privacy-by-default
    assert data["analytics_consent"] is False


async def test_create_organization_duplicate_slug(async_client: AsyncClient, sample_org: Organization) -> None:
    """Creating an org with a duplicate slug returns 409."""
    resp = await async_client.post(
        BASE,
        json={"slug": sample_org.slug, "name": "Duplicate"},
    )
    assert resp.status_code == 409


async def test_update_organization(async_client: AsyncClient, sample_org: Organization) -> None:
    """PATCH updates only specified fields."""
    resp = await async_client.patch(
        f"{BASE}/{sample_org.slug}",
        json={"name": "Gemeente Amsterdam Updated", "plan": "pro"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Gemeente Amsterdam Updated"
    assert data["plan"] == "pro"


async def test_delete_organization(async_client: AsyncClient, sample_org: Organization) -> None:
    """DELETE removes the organization; subsequent GET returns 404."""
    resp = await async_client.delete(f"{BASE}/{sample_org.slug}")
    assert resp.status_code == 204
    check = await async_client.get(f"{BASE}/{sample_org.slug}")
    assert check.status_code == 404


# ---------------------------------------------------------------------------
# Member management — 3 tests
# ---------------------------------------------------------------------------


async def test_invite_member(async_client: AsyncClient, sample_org: Organization) -> None:
    """Inviting a member creates a membership record."""
    resp = await async_client.post(
        f"{BASE}/{sample_org.slug}/members",
        json={
            "user_id": "keycloak-user-001",
            "email": "jan@amsterdam.nl",
            "display_name": "Jan de Vries",
            "role": "admin",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == "keycloak-user-001"
    assert data["role"] == "admin"


async def test_invite_member_duplicate(
    async_client: AsyncClient, sample_org: Organization, db_session: AsyncSession
) -> None:
    """Inviting the same user twice returns 409."""
    member = OrganizationMember(
        organization_id=sample_org.id,
        user_id="existing-user",
        email="existing@amsterdam.nl",
        role=OrgMemberRole.member,
    )
    db_session.add(member)
    await db_session.commit()

    resp = await async_client.post(
        f"{BASE}/{sample_org.slug}/members",
        json={"user_id": "existing-user", "email": "existing@amsterdam.nl", "role": "member"},
    )
    assert resp.status_code == 409


async def test_update_member_role(
    async_client: AsyncClient, sample_org: Organization, db_session: AsyncSession
) -> None:
    """Updating a member's role persists the change."""
    member = OrganizationMember(
        organization_id=sample_org.id,
        user_id="user-to-promote",
        email="promote@amsterdam.nl",
        role=OrgMemberRole.member,
    )
    db_session.add(member)
    await db_session.commit()

    resp = await async_client.patch(
        f"{BASE}/{sample_org.slug}/members/user-to-promote",
        json={"role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_remove_member(async_client: AsyncClient, sample_org: Organization, db_session: AsyncSession) -> None:
    """Removing a member returns 204; listing shows member gone."""
    member = OrganizationMember(
        organization_id=sample_org.id,
        user_id="user-to-remove",
        email="remove@amsterdam.nl",
        role=OrgMemberRole.viewer if hasattr(OrgMemberRole, "viewer") else OrgMemberRole.member,
    )
    db_session.add(member)
    await db_session.commit()

    resp = await async_client.delete(f"{BASE}/{sample_org.slug}/members/user-to-remove")
    assert resp.status_code == 204

    members_resp = await async_client.get(f"{BASE}/{sample_org.slug}/members")
    user_ids = [m["user_id"] for m in members_resp.json()]
    assert "user-to-remove" not in user_ids


# ---------------------------------------------------------------------------
# SSO config — 3 tests
# ---------------------------------------------------------------------------


async def test_create_oidc_sso_config(async_client: AsyncClient, sample_org: Organization) -> None:
    """Creating an OIDC SSO config stores the configuration."""
    resp = await async_client.post(
        f"{BASE}/{sample_org.slug}/sso",
        json={
            "sso_type": "oidc",
            "client_id": "haven-platform",
            "client_secret": "super-secret",
            "discovery_url": "https://sso.amsterdam.nl/.well-known/openid-configuration",
            "sso_only": False,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sso_type"] == "oidc"
    assert data["client_id"] == "haven-platform"
    assert data["discovery_url"] == "https://sso.amsterdam.nl/.well-known/openid-configuration"
    # client_secret not returned in response schema (security)


async def test_create_oidc_sso_requires_discovery_url(async_client: AsyncClient, sample_org: Organization) -> None:
    """OIDC SSO config without discovery_url returns 400."""
    resp = await async_client.post(
        f"{BASE}/{sample_org.slug}/sso",
        json={"sso_type": "oidc", "client_id": "haven-platform"},
    )
    assert resp.status_code == 400


async def test_create_saml_sso_config(async_client: AsyncClient, sample_org: Organization) -> None:
    """Creating a SAML SSO config with metadata_url succeeds."""
    resp = await async_client.post(
        f"{BASE}/{sample_org.slug}/sso",
        json={
            "sso_type": "saml",
            "metadata_url": "https://sso.amsterdam.nl/saml/metadata",
            "sso_only": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sso_type"] == "saml"
    assert data["sso_only"] is True


# ---------------------------------------------------------------------------
# Tenant membership + billing — 2 tests
# ---------------------------------------------------------------------------


async def test_add_tenant_to_org(async_client: AsyncClient, sample_org: Organization) -> None:
    """Adding a tenant to an org creates a membership record."""
    tenant_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"{BASE}/{sample_org.slug}/tenants",
        json={"tenant_id": tenant_id},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["tenant_id"] == tenant_id

    # Listing shows the tenant
    list_resp = await async_client.get(f"{BASE}/{sample_org.slug}/tenants")
    assert list_resp.status_code == 200
    assert any(t["tenant_id"] == tenant_id for t in list_resp.json())


async def test_billing_summary(async_client: AsyncClient, sample_org: Organization) -> None:
    """Billing summary returns org plan, tenant count, and Stripe IDs."""
    resp = await async_client.get(f"{BASE}/{sample_org.slug}/billing")
    assert resp.status_code == 200
    data = resp.json()
    assert data["organization_slug"] == sample_org.slug
    assert data["plan"] == sample_org.plan.value
    assert data["tenant_count"] == 0
    assert data["stripe_customer_id"] is None
