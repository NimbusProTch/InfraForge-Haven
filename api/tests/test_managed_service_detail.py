"""Tests for enriched managed service responses — runtime details, connected apps, error messages."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.application import Application
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType

# ---------------------------------------------------------------------------
# Enriched GET /services/{name} — runtime details
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_service_returns_runtime_details(async_client, db_session, sample_tenant):
    """GET single service includes runtime details from Everest."""
    svc = ManagedService(
        tenant_id=sample_tenant.id,
        name="detail-pg",
        service_type=ServiceType.POSTGRES,
        tier=ServiceTier.DEV,
        status=ServiceStatus.PROVISIONING,
        service_namespace="everest",
        secret_name="everest-secrets-detail-pg",
    )
    db_session.add(svc)
    await db_session.commit()

    # Mock the Everest sync_details call
    mock_details = {
        "status": "ready",
        "engine_version": "17.7",
        "replicas": 1,
        "ready_replicas": 1,
        "storage": "1Gi",
        "cpu": "600m",
        "memory": "512Mi",
        "hostname": "detail-pg-pgbouncer.everest.svc",
        "port": 5432,
        "error_message": None,
    }

    with patch("app.routers.services.ManagedServiceProvisioner") as MockProv:
        instance = MockProv.return_value
        instance.sync_details = AsyncMock(return_value=mock_details)

        # sync_details should also update service status to READY
        async def side_effect(s, tenant_namespace=""):
            s.status = ServiceStatus.READY
            return mock_details

        instance.sync_details.side_effect = side_effect

        response = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/services/detail-pg")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "detail-pg"
    assert data["runtime"] is not None
    assert data["runtime"]["engine_version"] == "17.7"
    assert data["runtime"]["hostname"] == "detail-pg-pgbouncer.everest.svc"
    assert data["runtime"]["port"] == 5432
    assert data["runtime"]["storage"] == "1Gi"
    assert data["runtime"]["cpu"] == "600m"


@pytest.mark.asyncio
async def test_get_service_returns_connected_apps(async_client, db_session, sample_tenant):
    """GET single service includes list of apps connected to this service."""
    svc = ManagedService(
        tenant_id=sample_tenant.id,
        name="connected-pg",
        service_type=ServiceType.POSTGRES,
        tier=ServiceTier.DEV,
        status=ServiceStatus.READY,
        service_namespace="everest",
        secret_name="everest-secrets-connected-pg",
    )
    db_session.add(svc)

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="my-web-app",
        name="My Web App",
        repo_url="https://github.com/org/repo",
        branch="main",
        env_from_secrets=[{"service_name": "connected-pg", "secret_name": "everest-secrets-connected-pg"}],
    )
    db_session.add(app_obj)
    await db_session.commit()

    with patch("app.routers.services.ManagedServiceProvisioner") as MockProv:
        instance = MockProv.return_value
        instance.sync_details = AsyncMock(return_value=None)

        response = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/services/connected-pg")

    assert response.status_code == 200
    data = response.json()
    assert len(data["connected_apps"]) == 1
    assert data["connected_apps"][0]["slug"] == "my-web-app"
    assert data["connected_apps"][0]["name"] == "My Web App"


@pytest.mark.asyncio
async def test_get_service_returns_empty_connected_apps(async_client, db_session, sample_tenant):
    """GET single service with no connected apps returns empty list."""
    svc = ManagedService(
        tenant_id=sample_tenant.id,
        name="solo-pg",
        service_type=ServiceType.POSTGRES,
        tier=ServiceTier.DEV,
        status=ServiceStatus.READY,
    )
    db_session.add(svc)
    await db_session.commit()

    with patch("app.routers.services.ManagedServiceProvisioner") as MockProv:
        instance = MockProv.return_value
        instance.sync_details = AsyncMock(return_value=None)

        response = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/services/solo-pg")

    assert response.status_code == 200
    data = response.json()
    assert data["connected_apps"] == []


# ---------------------------------------------------------------------------
# UPDATING status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_service_transitions_to_updating(async_client, db_session, sample_tenant):
    """PATCH on a ready service should set status to updating."""
    svc = ManagedService(
        tenant_id=sample_tenant.id,
        name="update-pg",
        service_type=ServiceType.POSTGRES,
        tier=ServiceTier.DEV,
        status=ServiceStatus.READY,
        service_namespace="everest",
        secret_name="everest-secrets-update-pg",
    )
    db_session.add(svc)
    await db_session.commit()

    with patch("app.routers.services.ManagedServiceProvisioner") as MockProv:
        instance = MockProv.return_value

        async def mock_update(s, **kwargs):
            s.status = ServiceStatus.UPDATING

        instance.update = AsyncMock(side_effect=mock_update)

        response = await async_client.patch(
            f"/api/v1/tenants/{sample_tenant.slug}/services/update-pg",
            json={"storage": "2Gi"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updating"


@pytest.mark.asyncio
async def test_patch_not_ready_service_returns_409(async_client, db_session, sample_tenant):
    """PATCH on a provisioning service should return 409."""
    svc = ManagedService(
        tenant_id=sample_tenant.id,
        name="notready-pg",
        service_type=ServiceType.POSTGRES,
        tier=ServiceTier.DEV,
        status=ServiceStatus.PROVISIONING,
    )
    db_session.add(svc)
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/tenants/{sample_tenant.slug}/services/notready-pg",
        json={"storage": "2Gi"},
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Error message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_message_shown_on_failure(async_client, db_session, sample_tenant):
    """Failed service should include error_message in response."""
    svc = ManagedService(
        tenant_id=sample_tenant.id,
        name="failed-pg",
        service_type=ServiceType.POSTGRES,
        tier=ServiceTier.DEV,
        status=ServiceStatus.FAILED,
        error_message="Insufficient storage quota",
    )
    db_session.add(svc)
    await db_session.commit()

    with patch("app.routers.services.ManagedServiceProvisioner") as MockProv:
        instance = MockProv.return_value
        instance.sync_details = AsyncMock(return_value=None)

        response = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/services/failed-pg")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["error_message"] == "Insufficient storage quota"


@pytest.mark.asyncio
async def test_list_services_includes_error_message(async_client, db_session, sample_tenant):
    """List endpoint also includes error_message."""
    svc = ManagedService(
        tenant_id=sample_tenant.id,
        name="err-pg",
        service_type=ServiceType.POSTGRES,
        tier=ServiceTier.DEV,
        status=ServiceStatus.FAILED,
        error_message="Connection refused",
    )
    db_session.add(svc)
    await db_session.commit()

    response = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/services")

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    found = next(s for s in data if s["name"] == "err-pg")
    assert found["error_message"] == "Connection refused"


# ---------------------------------------------------------------------------
# DATABASE_URL auto-inject on connect-service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_service_injects_database_url(async_client, db_session, sample_tenant):
    """Connecting a PostgreSQL service should auto-inject DATABASE_URL env var."""
    svc = ManagedService(
        tenant_id=sample_tenant.id,
        name="inject-pg",
        service_type=ServiceType.POSTGRES,
        tier=ServiceTier.DEV,
        status=ServiceStatus.READY,
        credentials_provisioned=True,
        service_namespace="everest",
        secret_name="everest-secrets-inject-pg",
        connection_hint="postgresql://inject-pg-app@inject-pg-rw.everest.svc:5432/inject_pg",
    )
    db_session.add(svc)

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="inject-app",
        name="Inject App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    response = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/inject-app/connect-service",
        json={"service_name": "inject-pg"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "DATABASE_URL" in data.get("env_vars", {})
    assert "inject-pg-rw.everest.svc:5432" in data["env_vars"]["DATABASE_URL"]


@pytest.mark.asyncio
async def test_connect_mysql_injects_mysql_url(async_client, db_session, sample_tenant):
    """Connecting a MySQL service should inject MYSQL_URL and DATABASE_URL."""
    svc = ManagedService(
        tenant_id=sample_tenant.id,
        name="inject-mysql",
        service_type=ServiceType.MYSQL,
        tier=ServiceTier.DEV,
        status=ServiceStatus.READY,
        credentials_provisioned=True,
        service_namespace="everest",
        secret_name="everest-secrets-inject-mysql",
        connection_hint="mysql://inject-mysql-pxc@inject-mysql-haproxy.everest.svc:3306/inject_mysql",
    )
    db_session.add(svc)

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="mysql-app",
        name="MySQL App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    response = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/mysql-app/connect-service",
        json={"service_name": "inject-mysql"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "MYSQL_URL" in data.get("env_vars", {})
    assert "DATABASE_URL" in data.get("env_vars", {})
