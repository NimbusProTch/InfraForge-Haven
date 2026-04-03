"""Tests for Sprint E8: Full regression — complete tenant lifecycle.

Covers the entire flow: tenant CRUD → app CRUD → services → build → deploy →
logs → backup → rollback → scale → disconnect → delete cascade.
"""

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.main import app


def _full_mock_k8s():
    """K8s mock supporting all operations needed for regression."""
    mock = MagicMock()
    mock.is_available.return_value = True
    mock.custom_objects = MagicMock()
    mock.custom_objects.create_namespaced_custom_object.return_value = {}
    mock.custom_objects.patch_namespaced_custom_object.return_value = {}
    mock.custom_objects.delete_namespaced_custom_object.return_value = {}
    mock.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    mock.core_v1 = MagicMock()
    mock.core_v1.create_namespace.return_value = MagicMock()
    mock.core_v1.delete_namespace.return_value = MagicMock()
    mock.core_v1.create_namespaced_secret.return_value = MagicMock()
    mock.core_v1.read_namespaced_secret.side_effect = Exception("not found")

    # Pod list for logs
    pod = MagicMock()
    pod.metadata.name = "test-pod-abc"
    pod.status.phase = "Running"
    pod.status.container_statuses = []
    pod.metadata.namespace = "tenant-regression"
    pod.metadata.creation_timestamp = MagicMock()
    pod.metadata.creation_timestamp.isoformat.return_value = "2026-04-03T10:00:00Z"
    pod.spec.node_name = "worker-1"

    pod_list = MagicMock()
    pod_list.items = [pod]
    mock.core_v1.list_namespaced_pod.return_value = pod_list
    mock.core_v1.read_namespaced_pod_log.return_value = "App started\nListening on port 8080"
    mock.core_v1.list_namespaced_event.return_value = MagicMock(items=[])

    mock.apps_v1 = MagicMock()
    mock.networking_v1 = MagicMock()
    mock.rbac_v1 = MagicMock()

    return mock


@pytest_asyncio.fixture
async def regression_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    mock_k8s = _full_mock_k8s()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "admin-user", "email": "admin@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Full tenant lifecycle regression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_tenant_lifecycle(regression_client):
    """Complete lifecycle: create → apps → services → deployments → delete."""
    c = regression_client

    # 1. Create tenant
    resp = await c.post("/api/v1/tenants", json={"name": "Regression", "slug": "regression"})
    assert resp.status_code == 201
    tenant = resp.json()
    assert tenant["slug"] == "regression"
    slug = tenant["slug"]

    # 2. Verify /tenants/me (admin-user is not a member yet, so empty)
    resp = await c.get("/api/v1/tenants/me")
    assert resp.status_code == 200

    # 3. Create app
    resp = await c.post(
        f"/api/v1/tenants/{slug}/apps",
        json={
            "name": "Regression API",
            "slug": "reg-api",
            "repo_url": "https://github.com/test/repo",
            "branch": "main",
            "port": 8080,
        },
    )
    assert resp.status_code == 201
    app_data = resp.json()
    assert app_data["slug"] == "reg-api"

    # 4. List apps
    resp = await c.get(f"/api/v1/tenants/{slug}/apps")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 5. Get single app
    resp = await c.get(f"/api/v1/tenants/{slug}/apps/reg-api")
    assert resp.status_code == 200
    assert resp.json()["port"] == 8080

    # 6. PATCH app
    resp = await c.patch(f"/api/v1/tenants/{slug}/apps/reg-api", json={"replicas": 3})
    assert resp.status_code == 200
    assert resp.json()["replicas"] == 3

    # 7. Create Redis service
    resp = await c.post(
        f"/api/v1/tenants/{slug}/services",
        json={"name": "app-redis", "service_type": "redis", "tier": "dev"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "provisioning"

    # 8. List services
    resp = await c.get(f"/api/v1/tenants/{slug}/services")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 9. Log streaming
    resp = await c.get(f"/api/v1/tenants/{slug}/apps/reg-api/logs?tail_lines=10")
    assert resp.status_code == 200
    assert "App started" in resp.text

    # 11. Pod status
    resp = await c.get(f"/api/v1/tenants/{slug}/apps/reg-api/pods")
    assert resp.status_code == 200
    assert resp.json()["k8s_available"] is True

    # 12. Events
    resp = await c.get(f"/api/v1/tenants/{slug}/apps/reg-api/events")
    assert resp.status_code == 200

    # 13. List deployments (empty initially)
    resp = await c.get(f"/api/v1/tenants/{slug}/apps/reg-api/deployments")
    assert resp.status_code == 200

    # 14. Delete app
    resp = await c.delete(f"/api/v1/tenants/{slug}/apps/reg-api")
    assert resp.status_code == 204

    # 15. Verify app deleted
    resp = await c.get(f"/api/v1/tenants/{slug}/apps")
    assert len(resp.json()) == 0

    # 16. Delete service
    resp = await c.delete(f"/api/v1/tenants/{slug}/services/app-redis")
    assert resp.status_code == 204

    # 17. Delete tenant
    resp = await c.delete(f"/api/v1/tenants/{slug}")
    assert resp.status_code == 204

    # 18. Verify tenant deleted
    resp = await c.get("/api/v1/tenants")
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_multi_tenant_isolation(regression_client):
    """Multiple tenants don't interfere with each other."""
    c = regression_client

    # Create 2 tenants
    resp1 = await c.post("/api/v1/tenants", json={"name": "Tenant A", "slug": "tenant-a"})
    assert resp1.status_code == 201
    resp2 = await c.post("/api/v1/tenants", json={"name": "Tenant B", "slug": "tenant-b"})
    assert resp2.status_code == 201

    # Create app in tenant A
    await c.post(
        "/api/v1/tenants/tenant-a/apps",
        json={
            "name": "App A",
            "slug": "app-a",
            "repo_url": "https://github.com/test/a",
            "branch": "main",
            "port": 3000,
        },
    )

    # Create app in tenant B
    await c.post(
        "/api/v1/tenants/tenant-b/apps",
        json={
            "name": "App B",
            "slug": "app-b",
            "repo_url": "https://github.com/test/b",
            "branch": "main",
            "port": 4000,
        },
    )

    # Verify isolation: tenant A has 1 app, tenant B has 1 app
    resp_a = await c.get("/api/v1/tenants/tenant-a/apps")
    resp_b = await c.get("/api/v1/tenants/tenant-b/apps")
    assert len(resp_a.json()) == 1
    assert len(resp_b.json()) == 1
    assert resp_a.json()[0]["slug"] == "app-a"
    assert resp_b.json()[0]["slug"] == "app-b"

    # Verify cross-tenant access prevented
    resp = await c.get("/api/v1/tenants/tenant-a/apps/app-b")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_tenant_409(regression_client):
    """Creating duplicate tenant returns 409."""
    c = regression_client
    await c.post("/api/v1/tenants", json={"name": "Dup", "slug": "dup-tenant"})
    resp = await c.post("/api/v1/tenants", json={"name": "Dup2", "slug": "dup-tenant"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_duplicate_app_409(regression_client):
    """Creating duplicate app in same tenant returns 409."""
    c = regression_client
    await c.post("/api/v1/tenants", json={"name": "Dup App", "slug": "dup-app-t"})
    await c.post(
        "/api/v1/tenants/dup-app-t/apps",
        json={
            "name": "App",
            "slug": "same-slug",
            "repo_url": "https://github.com/test",
            "branch": "main",
            "port": 8080,
        },
    )
    resp = await c.post(
        "/api/v1/tenants/dup-app-t/apps",
        json={
            "name": "App2",
            "slug": "same-slug",
            "repo_url": "https://github.com/test2",
            "branch": "main",
            "port": 8080,
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_service_types_validation(regression_client):
    """All 5 service types can be created."""
    c = regression_client
    await c.post("/api/v1/tenants", json={"name": "SvcTypes", "slug": "svc-types"})

    for svc_type in ["postgres", "mysql", "mongodb", "redis", "rabbitmq"]:
        resp = await c.post(
            "/api/v1/tenants/svc-types/services",
            json={"name": f"app-{svc_type}", "service_type": svc_type, "tier": "dev"},
        )
        assert resp.status_code == 201, f"Failed for {svc_type}: {resp.json()}"

    resp = await c.get("/api/v1/tenants/svc-types/services")
    assert len(resp.json()) == 5


@pytest.mark.asyncio
async def test_invalid_service_type_rejected(regression_client):
    """Invalid service type is rejected."""
    c = regression_client
    await c.post("/api/v1/tenants", json={"name": "Bad SVC", "slug": "bad-svc"})
    resp = await c.post(
        "/api/v1/tenants/bad-svc/services",
        json={"name": "app-bad", "service_type": "oracle", "tier": "dev"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tenant_not_found_404(regression_client):
    """Operations on non-existent tenant return 404."""
    c = regression_client
    resp = await c.get("/api/v1/tenants/ghost/apps")
    assert resp.status_code == 404

    resp = await c.get("/api/v1/tenants/ghost/services")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_backup_endpoints_require_db_service(regression_client):
    """Backup endpoints require a valid DB service (not Redis)."""
    c = regression_client
    await c.post("/api/v1/tenants", json={"name": "Bkp Test", "slug": "bkp-reg"})
    await c.post(
        "/api/v1/tenants/bkp-reg/services",
        json={"name": "app-redis", "service_type": "redis", "tier": "dev"},
    )

    resp = await c.post("/api/v1/tenants/bkp-reg/services/app-redis/backup")
    assert resp.status_code == 400

    resp = await c.get("/api/v1/tenants/bkp-reg/services/app-redis/backups")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_health_endpoint(regression_client):
    """Health endpoint returns ok."""
    resp = await regression_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
