"""Tests for canary deployment endpoints."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.tenant import Tenant

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_tenant_and_app(db: AsyncSession, app_slug: str = "canary-app") -> tuple[Tenant, Application]:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="canary-tenant",
        name="Canary Tenant",
        namespace="tenant-canary-tenant",
        keycloak_realm="canary-tenant",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(tenant)
    await db.flush()

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug=app_slug,
        name="Canary App",
        repo_url="https://github.com/org/repo",
        branch="main",
        resource_cpu_limit="500m",
        resource_memory_limit="256Mi",
        resource_cpu_request="100m",
        resource_memory_request="64Mi",
    )
    db.add(app_obj)
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(app_obj)
    return tenant, app_obj


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_canary_status_disabled(async_client, db_session):
    """GET canary returns disabled status for a fresh app."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    response = await async_client.get(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/canary"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["weight"] == 10  # default


@pytest.mark.asyncio
async def test_enable_canary_sets_flag(async_client, db_session):
    """PUT canary with enabled=true and canary_image updates DB flags."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    response = await async_client.put(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/canary",
        json={"enabled": True, "weight": 20, "canary_image": "myimage:canary"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["weight"] == 20


@pytest.mark.asyncio
async def test_enable_canary_requires_image_on_first_enable(async_client, db_session):
    """PUT canary with enabled=true but no canary_image returns 422."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    response = await async_client.put(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/canary",
        json={"enabled": True, "weight": 10},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_disable_canary(async_client, db_session):
    """PUT canary with enabled=false disables the canary."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    # Enable first
    await async_client.put(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/canary",
        json={"enabled": True, "weight": 30, "canary_image": "myimage:canary"},
    )

    # Now disable
    response = await async_client.put(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/canary",
        json={"enabled": False, "weight": 30},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False


@pytest.mark.asyncio
async def test_promote_canary(async_client, db_session):
    """POST /canary/promote succeeds when canary is enabled."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    # Enable canary first
    await async_client.put(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/canary",
        json={"enabled": True, "weight": 50, "canary_image": "myimage:v2"},
    )

    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/canary/promote"
    )
    assert response.status_code == 200
    data = response.json()
    assert "promoted" in str(data).lower() or data.get("status") is not None


@pytest.mark.asyncio
async def test_rollback_canary(async_client, db_session):
    """POST /canary/rollback succeeds when canary is enabled."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    await async_client.put(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/canary",
        json={"enabled": True, "weight": 50, "canary_image": "myimage:v2"},
    )

    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/canary/rollback"
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_canary_404_for_unknown_app(async_client, db_session):
    """Canary endpoints return 404 for unknown app slug."""
    tenant, _app = await _make_tenant_and_app(db_session)

    response = await async_client.get(
        f"/api/v1/tenants/{tenant.slug}/apps/nonexistent/canary"
    )
    assert response.status_code == 404
