"""Tests for PVC (Persistent Volume Claim) / volumes endpoints."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember


async def _make_tenant_and_app(db: AsyncSession) -> tuple[Tenant, Application]:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="pvc-tenant",
        name="PVC Tenant",
        namespace="tenant-pvc-tenant",
        keycloak_realm="pvc-tenant",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(tenant)
    await db.flush()
    # H0-9: pvcs router now enforces membership
    db.add(TenantMember(tenant_id=tenant.id, user_id="test-user", email="test@haven.nl", role=MemberRole("owner")))

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="pvc-app",
        name="PVC App",
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


@pytest.mark.asyncio
async def test_list_volumes_empty_without_k8s(async_client, db_session):
    """List volumes returns empty list when K8s is unavailable."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    response = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/volumes")
    assert response.status_code == 200
    data = response.json()
    assert data["k8s_available"] is False
    assert data["volumes"] == []


@pytest.mark.asyncio
async def test_create_volume_persisted_to_db(async_client, db_session):
    """POST creates a volume spec and persists it to the application."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/volumes",
        json={
            "name": "data",
            "mount_path": "/data",
            "size_gi": 10,
            "storage_class": "longhorn",
            "access_mode": "ReadWriteOnce",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "data"
    assert data["size_gi"] == 10
    assert data["mount_path"] == "/data"


@pytest.mark.asyncio
async def test_create_duplicate_volume_returns_409(async_client, db_session):
    """POST with a duplicate volume name returns 409."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    vol_payload = {"name": "uploads", "mount_path": "/uploads", "size_gi": 5}

    await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/volumes",
        json=vol_payload,
    )
    # Second identical request
    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/volumes",
        json=vol_payload,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_volume(async_client, db_session):
    """DELETE removes the volume spec from the app."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/volumes",
        json={"name": "tmp-vol", "mount_path": "/tmp/data", "size_gi": 2},
    )

    del_resp = await async_client.delete(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/volumes/tmp-vol")
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_nonexistent_volume_returns_404(async_client, db_session):
    """DELETE a volume name that doesn't exist returns 404."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    response = await async_client.delete(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/volumes/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_volume_tenant_404(async_client, db_session):
    """Volume endpoints return 404 for unknown tenant."""
    response = await async_client.get("/api/v1/tenants/ghost-tenant/apps/ghost-app/volumes")
    assert response.status_code == 404
