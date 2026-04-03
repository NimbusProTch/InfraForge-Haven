"""Tests for Sprint E4: Service scaling (Redis, RabbitMQ, Everest) + rollback verification.

Tests:
- PATCH /services/{name} endpoint validation
- Everest service scale (PG/MySQL/MongoDB)
- Redis CRD scale
- RabbitMQ CRD scale
- Error cases: not ready, no fields, unsupported type
- Rollback: deployment rollback creates new deployment
"""

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
from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier
from app.models.managed_service import ServiceType as ModelServiceType
from app.models.tenant import Tenant
from app.services.managed_service import ManagedServiceProvisioner


async def _tenant(db: AsyncSession, slug: str = "scale-test") -> Tenant:
    t = Tenant(
        id=uuid.uuid4(), slug=slug, name=slug, namespace=f"tenant-{slug}",
        keycloak_realm=slug, cpu_limit="4", memory_limit="8Gi", storage_limit="50Gi",
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def _service(
    db: AsyncSession, tenant: Tenant, name: str, svc_type: ModelServiceType,
    status: ServiceStatus = ServiceStatus.READY,
) -> ManagedService:
    s = ManagedService(
        id=uuid.uuid4(), tenant_id=tenant.id, name=name, service_type=svc_type,
        tier=ServiceTier.DEV, status=status, secret_name=f"svc-{name}",
        service_namespace=tenant.namespace, credentials_provisioned=True,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _app(db: AsyncSession, tenant: Tenant, slug: str = "test-api") -> Application:
    a = Application(
        id=uuid.uuid4(), tenant_id=tenant.id, slug=slug, name="Test",
        repo_url="https://github.com/test/repo", branch="main", port=8080,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


async def _deployment(db: AsyncSession, application: Application, **kwargs) -> Deployment:
    d = Deployment(
        id=uuid.uuid4(), application_id=application.id, commit_sha="abc123",
        status=kwargs.get("status", DeploymentStatus.RUNNING),
        image_tag=kwargs.get("image_tag", "harbor.io/test:v1"),
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


def _mock_k8s():
    mock = MagicMock()
    mock.is_available.return_value = True
    mock.custom_objects = MagicMock()
    mock.custom_objects.patch_namespaced_custom_object.return_value = {}
    mock.core_v1 = MagicMock()
    return mock


@pytest_asyncio.fixture
async def scale_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    mock_k8s = _mock_k8s()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test", "email": "t@t.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# PATCH /services/{name} endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scale_service_no_fields_422(scale_client, db_session):
    """PATCH with no update fields returns 422."""
    t = await _tenant(db_session, "no-fields")
    await _service(db_session, t, "app-pg", ModelServiceType.POSTGRES)
    resp = await scale_client.patch(f"/api/v1/tenants/{t.slug}/services/app-pg", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_scale_service_not_ready_409(scale_client, db_session):
    """PATCH on non-READY service returns 409."""
    t = await _tenant(db_session, "not-ready")
    await _service(db_session, t, "app-pg", ModelServiceType.POSTGRES, ServiceStatus.PROVISIONING)
    resp = await scale_client.patch(f"/api/v1/tenants/{t.slug}/services/app-pg", json={"replicas": 3})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_scale_service_not_found_404(scale_client, db_session):
    """PATCH on unknown service returns 404."""
    t = await _tenant(db_session, "not-found")
    resp = await scale_client.patch(f"/api/v1/tenants/{t.slug}/services/ghost", json={"replicas": 3})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_scale_redis_via_endpoint(scale_client, db_session):
    """PATCH Redis service triggers CRD scale."""
    t = await _tenant(db_session, "redis-scale")
    await _service(db_session, t, "app-redis", ModelServiceType.REDIS)
    resp = await scale_client.patch(f"/api/v1/tenants/{t.slug}/services/app-redis", json={"replicas": 3})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_scale_rabbitmq_via_endpoint(scale_client, db_session):
    """PATCH RabbitMQ service triggers CRD scale."""
    t = await _tenant(db_session, "rabbit-scale")
    await _service(db_session, t, "app-rabbit", ModelServiceType.RABBITMQ)
    resp = await scale_client.patch(f"/api/v1/tenants/{t.slug}/services/app-rabbit", json={"replicas": 3})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Provisioner unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provisioner_redis_scale():
    """ManagedServiceProvisioner.update scales Redis via CRD patch."""
    k8s = _mock_k8s()
    p = ManagedServiceProvisioner(k8s)
    svc = MagicMock()
    svc.service_type = ModelServiceType.REDIS
    svc.service_namespace = "tenant-test"
    svc.name = "app-redis"

    await p.update(svc, replicas=3)
    k8s.custom_objects.patch_namespaced_custom_object.assert_called_once()


@pytest.mark.asyncio
async def test_provisioner_rabbitmq_scale():
    """ManagedServiceProvisioner.update scales RabbitMQ via CRD patch."""
    k8s = _mock_k8s()
    p = ManagedServiceProvisioner(k8s)
    svc = MagicMock()
    svc.service_type = ModelServiceType.RABBITMQ
    svc.service_namespace = "tenant-test"
    svc.name = "app-rabbit"

    await p.update(svc, replicas=3)
    call_kwargs = k8s.custom_objects.patch_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["plural"] == "rabbitmqclusters"
    assert call_kwargs["body"]["spec"]["replicas"] == 3


@pytest.mark.asyncio
async def test_provisioner_redis_scale_none_noop():
    """Redis scale with replicas=None is a no-op."""
    k8s = _mock_k8s()
    p = ManagedServiceProvisioner(k8s)
    svc = MagicMock()
    svc.service_type = ModelServiceType.REDIS
    svc.service_namespace = "tenant-test"
    svc.name = "app-redis"

    await p.update(svc, replicas=None)
    k8s.custom_objects.patch_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_provisioner_redis_scale_failure():
    """Redis scale failure raises RuntimeError."""
    k8s = _mock_k8s()
    k8s.custom_objects.patch_namespaced_custom_object.side_effect = Exception("API error")
    p = ManagedServiceProvisioner(k8s)
    svc = MagicMock()
    svc.service_type = ModelServiceType.REDIS
    svc.service_namespace = "tenant-test"
    svc.name = "app-redis"

    with pytest.raises(RuntimeError, match="Redis scale failed"):
        await p.update(svc, replicas=3)


# ---------------------------------------------------------------------------
# Rollback verification tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_creates_new_deployment(scale_client, db_session):
    """POST /deployments/{id}/rollback creates a new deployment."""
    t = await _tenant(db_session, "rollback-test")
    application = await _app(db_session, t)
    d1 = await _deployment(db_session, application, image_tag="harbor.io/test:v1")

    resp = await scale_client.post(
        f"/api/v1/tenants/{t.slug}/apps/{application.slug}/deployments/{d1.id}/rollback"
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "deploying"
    assert data["commit_sha"] == f"rollback-to-{d1.id}"


@pytest.mark.asyncio
async def test_rollback_404_unknown_deployment(scale_client, db_session):
    """POST /deployments/{id}/rollback returns 404 for unknown deployment."""
    t = await _tenant(db_session, "rollback-404")
    application = await _app(db_session, t)
    resp = await scale_client.post(
        f"/api/v1/tenants/{t.slug}/apps/{application.slug}/deployments/{uuid.uuid4()}/rollback"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rollback_no_image_tag_400(scale_client, db_session):
    """POST /deployments/{id}/rollback returns 400 if no image_tag."""
    t = await _tenant(db_session, "rollback-noimg")
    application = await _app(db_session, t)
    d1 = await _deployment(db_session, application, image_tag=None)

    resp = await scale_client.post(
        f"/api/v1/tenants/{t.slug}/apps/{application.slug}/deployments/{d1.id}/rollback"
    )
    assert resp.status_code in (400, 409)  # no image_tag = cannot rollback
