"""Tests for backup endpoints."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.main import app
from app.models.tenant import Tenant


async def _make_tenant(db: AsyncSession) -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="bkp-tenant",
        name="Backup Tenant",
        namespace="tenant-bkp-tenant",
        keycloak_realm="bkp-tenant",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def k8s_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async client with K8s available."""
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_k8s.custom_objects = MagicMock()
    mock_k8s.custom_objects.create_namespaced_custom_object.return_value = {}
    mock_k8s.custom_objects.patch_namespaced_custom_object.return_value = {}

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test-user", "email": "test@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_backups_without_k8s(async_client, db_session):
    """List backups returns k8s_available=False when K8s is unavailable."""
    tenant = await _make_tenant(db_session)

    response = await async_client.get(f"/api/v1/tenants/{tenant.slug}/backup")
    assert response.status_code == 200
    data = response.json()
    assert data["k8s_available"] is False
    assert data["backups"] == []
    assert data["tenant_slug"] == tenant.slug


@pytest.mark.asyncio
async def test_trigger_backup_with_k8s(k8s_client, db_session):
    """POST /backup triggers backup and returns backup_name when K8s is available."""
    tenant = await _make_tenant(db_session)

    response = await k8s_client.post(f"/api/v1/tenants/{tenant.slug}/backup")
    assert response.status_code == 202
    data = response.json()
    assert "backup_name" in data
    assert "triggered_at" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_trigger_backup_without_k8s_returns_503(async_client, db_session):
    """POST /backup returns 503 when K8s is not available."""
    tenant = await _make_tenant(db_session)

    response = await async_client.post(f"/api/v1/tenants/{tenant.slug}/backup")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_backup_schedule_update(k8s_client, db_session):
    """PUT /backup/schedule updates the backup schedule."""
    tenant = await _make_tenant(db_session)

    response = await k8s_client.put(
        f"/api/v1/tenants/{tenant.slug}/backup/schedule",
        json={"schedule": "0 3 * * *", "retention_days": 14, "storage_location": "minio"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_backup_404_unknown_tenant(async_client):
    """Backup endpoints return 404 for unknown tenant."""
    response = await async_client.get("/api/v1/tenants/ghost-tenant/backup")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_trigger_backup_response_structure(k8s_client, db_session):
    """Backup trigger response has expected fields."""
    tenant = await _make_tenant(db_session)

    response = await k8s_client.post(f"/api/v1/tenants/{tenant.slug}/backup")
    data = response.json()

    assert isinstance(data["backup_name"], str)
    assert len(data["backup_name"]) > 0
    assert isinstance(data["triggered_at"], str)
    assert data["backup_name"].startswith("backup-bkp-tenant-")
