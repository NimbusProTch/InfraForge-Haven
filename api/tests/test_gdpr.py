"""GDPR / AVG compliance endpoint tests (Sprint 8).

Tests cover:
- Consent grant / revoke / list
- Data retention policy get / update
- Data export (Art. 20)
- Data erasure (Art. 17)
"""

import uuid

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.models.user_consent import ConsentType, UserConsent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_SLUG = "gdpr-gemeente"
BASE = f"/api/v1/tenants/{TENANT_SLUG}/gdpr"


@pytest_asyncio.fixture
async def gdpr_tenant(db_session: AsyncSession) -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=TENANT_SLUG,
        name="GDPR Gemeente",
        namespace=f"tenant-{TENANT_SLUG}",
        keycloak_realm=TENANT_SLUG,
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db_session.add(tenant)
    await db_session.flush()
    # H0-9: GDPR router now enforces membership
    db_session.add(
        TenantMember(tenant_id=tenant.id, user_id="test-user", email="test@haven.nl", role=MemberRole("owner"))
    )
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# Consent tests (4 tests)
# ---------------------------------------------------------------------------


async def test_list_consents_empty(async_client: AsyncClient, gdpr_tenant: Tenant) -> None:
    """Empty consent list for a fresh tenant."""
    resp = await async_client.get(f"{BASE}/consent")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_grant_consent(async_client: AsyncClient, gdpr_tenant: Tenant) -> None:
    """Granting a consent creates a record with granted=True."""
    resp = await async_client.post(
        f"{BASE}/consent",
        json={
            "consent_type": "data_processing",
            "ip_address": "192.168.1.1",
            "context": "User accepted DPA v1.0 at signup",
        },
        params={"user_id": "user-abc"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["consent_type"] == "data_processing"
    assert data["granted"] is True
    assert data["ip_address"] == "192.168.1.1"
    assert data["revoked_at"] is None


async def test_revoke_consent(async_client: AsyncClient, gdpr_tenant: Tenant) -> None:
    """Revoking a consent creates a new record with granted=False and revoked_at set."""
    resp = await async_client.delete(
        f"{BASE}/consent/marketing",
        params={"user_id": "user-abc"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["consent_type"] == "marketing"
    assert data["granted"] is False
    assert data["revoked_at"] is not None


async def test_consent_not_found_on_unknown_tenant(async_client: AsyncClient) -> None:
    """Listing consents for a non-existent tenant returns 404."""
    resp = await async_client.get("/api/v1/tenants/unknown-slug/gdpr/consent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Data retention policy tests (2 tests)
# ---------------------------------------------------------------------------


async def test_get_retention_policy_creates_default(async_client: AsyncClient, gdpr_tenant: Tenant) -> None:
    """First GET auto-creates a default retention policy."""
    resp = await async_client.get(f"{BASE}/retention")
    assert resp.status_code == 200
    data = resp.json()
    assert data["audit_log_days"] == 365
    assert data["build_log_days"] == 30
    assert data["policy_version"] == "1.0"


async def test_update_retention_policy(async_client: AsyncClient, gdpr_tenant: Tenant) -> None:
    """PATCH updates specified fields; others remain at defaults."""
    await async_client.get(f"{BASE}/retention")  # ensure default exists

    resp = await async_client.patch(
        f"{BASE}/retention",
        json={"audit_log_days": 180, "notes": "Shortened for GDPR minimisation"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["audit_log_days"] == 180
    assert data["notes"] == "Shortened for GDPR minimisation"
    assert data["deployment_log_days"] == 90  # unchanged


# ---------------------------------------------------------------------------
# Data export tests (Art. 20) — 2 tests
# ---------------------------------------------------------------------------


async def test_export_data_empty_tenant(async_client: AsyncClient, gdpr_tenant: Tenant) -> None:
    """Export for a fresh tenant returns empty lists."""
    resp = await async_client.get(f"{BASE}/export", params={"user_id": "user-abc"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_slug"] == TENANT_SLUG
    assert data["requesting_user_id"] == "user-abc"
    assert data["applications"] == []
    assert data["consents"] == []


async def test_export_includes_consents(
    async_client: AsyncClient, gdpr_tenant: Tenant, db_session: AsyncSession
) -> None:
    """Export includes consent records."""
    consent = UserConsent(
        tenant_id=gdpr_tenant.id,
        user_id="user-xyz",
        consent_type=ConsentType.analytics,
        granted=True,
    )
    db_session.add(consent)
    await db_session.commit()

    resp = await async_client.get(f"{BASE}/export", params={"user_id": "user-xyz"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["consents"]) == 1
    assert data["consents"][0]["consent_type"] == "analytics"


# ---------------------------------------------------------------------------
# Data erasure tests (Art. 17) — 2 tests
# ---------------------------------------------------------------------------


async def test_erase_requires_confirmation(async_client: AsyncClient, gdpr_tenant: Tenant) -> None:
    """Erasure with wrong confirmation string returns 400."""
    resp = await async_client.post(
        f"{BASE}/erase",
        json={"confirm": "yes please delete"},
        params={"user_id": "user-abc"},
    )
    assert resp.status_code == 400


async def test_erase_deletes_tenant_and_data(
    async_client: AsyncClient, gdpr_tenant: Tenant, db_session: AsyncSession
) -> None:
    """Successful erasure removes tenant and all associated data."""
    # Add a consent record to verify it gets deleted
    consent = UserConsent(
        tenant_id=gdpr_tenant.id,
        user_id="user-abc",
        consent_type=ConsentType.data_processing,
        granted=True,
    )
    db_session.add(consent)
    await db_session.commit()

    resp = await async_client.post(
        f"{BASE}/erase",
        json={"confirm": "ERASE MY DATA"},
        params={"user_id": "user-abc"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_slug"] == TENANT_SLUG
    assert data["records_deleted"]["consents"] == 1

    # Tenant no longer exists
    check = await async_client.get(f"/api/v1/tenants/{TENANT_SLUG}")
    assert check.status_code == 404
