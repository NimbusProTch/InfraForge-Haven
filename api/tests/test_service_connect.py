"""Tests for service↔app connect/disconnect and service credentials endpoints."""

import uuid
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.k8s.client import K8sClient
from app.main import app
from app.models.application import Application
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType
from app.models.tenant import Tenant

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_k8s_with_secret() -> K8sClient:
    """K8s client that returns a fake secret when read_namespaced_secret is called."""
    import base64

    k8s = MagicMock(spec=K8sClient)
    k8s.is_available.return_value = True
    k8s.core_v1 = MagicMock()
    k8s.apps_v1 = MagicMock()
    k8s.batch_v1 = MagicMock()
    k8s.autoscaling_v2 = MagicMock()
    k8s.custom_objects = MagicMock()

    secret = MagicMock()
    secret.data = {
        "username": base64.b64encode(b"myuser").decode(),
        "password": base64.b64encode(b"s3cr3t").decode(),
        "host": base64.b64encode(b"my-pg-rw.tenant-test.svc").decode(),
    }
    k8s.core_v1.read_namespaced_secret.return_value = secret
    return k8s


@pytest.fixture
async def async_client_with_secret(db_session: AsyncSession, mock_k8s_with_secret: K8sClient):
    """Async client with K8s that can read secrets."""

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s_with_secret
    app.dependency_overrides[verify_token] = lambda: {"sub": "test-user", "email": "test@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def tenant_app_service(db_session: AsyncSession):
    """Create a tenant, an app, and a ready managed service."""
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="connect-tenant",
        name="Connect Tenant",
        namespace="tenant-connect-tenant",
        keycloak_realm="connect-tenant",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db_session.add(tenant)
    await db_session.flush()

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="connect-app",
        name="Connect App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)

    svc = ManagedService(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="my-pg",
        service_type=ServiceType.POSTGRES,
        tier=ServiceTier.DEV,
        status=ServiceStatus.READY,
        secret_name="my-pg-app",
        service_namespace="tenant-connect-tenant",
        connection_hint="postgresql://my_pg_user@my-pg-rw.tenant-connect-tenant.svc:5432/my_pg",
    )
    db_session.add(svc)

    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(app_obj)
    await db_session.refresh(svc)
    return tenant, app_obj, svc


# ---------------------------------------------------------------------------
# connect-service endpoint
# ---------------------------------------------------------------------------


async def test_connect_service_adds_env_from_secrets(async_client: AsyncClient, tenant_app_service):
    tenant, app_obj, svc = tenant_app_service
    resp = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/connect-service",
        json={"service_name": svc.name},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["env_from_secrets"] is not None
    assert len(data["env_from_secrets"]) == 1
    entry = data["env_from_secrets"][0]
    assert entry["service_name"] == "my-pg"
    assert entry["secret_name"] == "my-pg-app"
    assert entry["namespace"] == "tenant-connect-tenant"


async def test_connect_service_idempotent(async_client: AsyncClient, tenant_app_service):
    """Connecting the same service twice keeps only one entry."""
    tenant, app_obj, svc = tenant_app_service
    for _ in range(2):
        resp = await async_client.post(
            f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/connect-service",
            json={"service_name": svc.name},
        )
        assert resp.status_code == 200
    assert len(resp.json()["env_from_secrets"]) == 1


async def test_connect_service_not_found(async_client: AsyncClient, tenant_app_service):
    tenant, app_obj, _ = tenant_app_service
    resp = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/connect-service",
        json={"service_name": "nonexistent"},
    )
    assert resp.status_code == 404


async def test_connect_service_not_ready(async_client: AsyncClient, db_session: AsyncSession, tenant_app_service):
    """Cannot connect a service that is still provisioning."""
    tenant, app_obj, svc = tenant_app_service
    svc.status = ServiceStatus.PROVISIONING
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/connect-service",
        json={"service_name": svc.name},
    )
    assert resp.status_code == 409


async def test_disconnect_service_removes_entry(async_client: AsyncClient, tenant_app_service):
    tenant, app_obj, svc = tenant_app_service
    # First connect
    await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/connect-service",
        json={"service_name": svc.name},
    )
    # Then disconnect
    resp = await async_client.delete(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/connect-service/{svc.name}",
    )
    assert resp.status_code == 204

    # Verify it's gone
    get_resp = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}")
    assert get_resp.status_code == 200
    app_data = get_resp.json()
    assert not app_data.get("env_from_secrets")


async def test_disconnect_service_noop_if_not_connected(async_client: AsyncClient, tenant_app_service):
    """Disconnecting a service that was never connected returns 204 (idempotent)."""
    tenant, app_obj, _ = tenant_app_service
    resp = await async_client.delete(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/connect-service/nonexistent",
    )
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# credentials endpoint
# ---------------------------------------------------------------------------


async def test_get_credentials_returns_decoded_secret(async_client_with_secret: AsyncClient, tenant_app_service):
    tenant, _, svc = tenant_app_service
    resp = await async_client_with_secret.get(
        f"/api/v1/tenants/{tenant.slug}/services/{svc.name}/credentials",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["service_name"] == "my-pg"
    assert data["secret_name"] == "my-pg-app"
    assert data["connection_hint"] is not None
    assert data["credentials"]["username"] == "myuser"
    assert data["credentials"]["password"] == "s3cr3t"
    assert data["credentials"]["host"] == "my-pg-rw.tenant-test.svc"


async def test_get_credentials_503_when_k8s_unavailable(async_client: AsyncClient, tenant_app_service):
    """async_client uses mock_k8s which is unavailable — should return 503."""
    tenant, _, svc = tenant_app_service
    resp = await async_client.get(
        f"/api/v1/tenants/{tenant.slug}/services/{svc.name}/credentials",
    )
    assert resp.status_code == 503


async def test_get_credentials_service_not_found(async_client_with_secret: AsyncClient, tenant_app_service):
    tenant, _, _ = tenant_app_service
    resp = await async_client_with_secret.get(
        f"/api/v1/tenants/{tenant.slug}/services/nonexistent/credentials",
    )
    assert resp.status_code == 404


async def test_get_credentials_service_not_ready(
    async_client_with_secret: AsyncClient, db_session: AsyncSession, tenant_app_service
):
    tenant, _, svc = tenant_app_service
    svc.status = ServiceStatus.PROVISIONING
    await db_session.commit()

    resp = await async_client_with_secret.get(
        f"/api/v1/tenants/{tenant.slug}/services/{svc.name}/credentials",
    )
    assert resp.status_code == 409
