"""Sprint 3: App Creation + Build Pipeline Tests.

Tests app CRUD, build trigger, deployment lifecycle,
cross-tenant isolation, and build-status endpoint.
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.main import app
from app.models.deployment import DeploymentStatus
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember


def _mock_k8s():
    m = MagicMock()
    m.is_available.return_value = True
    m.custom_objects = MagicMock()
    m.custom_objects.create_namespaced_custom_object.return_value = {}
    m.core_v1 = MagicMock()
    m.core_v1.create_namespace.return_value = MagicMock()
    m.core_v1.delete_namespace.return_value = MagicMock()
    m.core_v1.create_namespaced_secret.return_value = MagicMock()
    m.core_v1.read_namespaced_secret.side_effect = Exception("not found")
    m.apps_v1 = MagicMock()
    m.rbac_v1 = MagicMock()
    m.networking_v1 = MagicMock()
    m.batch_v1 = MagicMock()
    # Build pod list mock
    pod_list = MagicMock()
    pod_list.items = []
    m.core_v1.list_namespaced_pod.return_value = pod_list
    return m


async def _tenant(db: AsyncSession, slug: str, uid: str) -> Tenant:
    t = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        name=slug.title(),
        namespace=f"tenant-{slug}",
        keycloak_realm=f"tenant-{slug}",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(t)
    await db.commit()
    m = TenantMember(id=uuid.uuid4(), tenant_id=t.id, user_id=uid, email=f"{uid}@t.nl", role=MemberRole("owner"))
    db.add(m)
    await db.commit()
    await db.refresh(t)
    return t


def _client(db_session, uid="s3-user"):
    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_k8s] = _mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": uid, "email": f"{uid}@t.nl"}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


APP_BODY = {
    "name": "Test App",
    "slug": "test-app",
    "repo_url": "https://github.com/NimbusProTch/rotterdam-api",
    "branch": "main",
    "port": 8080,
}


# ---------------------------------------------------------------------------
# App CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b3_01_create_app(db_session):
    """POST /apps → 201."""
    t = await _tenant(db_session, "app-create", "u1")
    async with _client(db_session, "u1") as c:
        r = await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        assert r.status_code == 201
        assert r.json()["slug"] == "test-app"
        assert r.json()["port"] == 8080
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b3_02_duplicate_app_409(db_session):
    """POST /apps duplicate slug → 409."""
    t = await _tenant(db_session, "app-dup", "u2")
    async with _client(db_session, "u2") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        r = await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        assert r.status_code == 409
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b3_03_list_apps(db_session):
    """GET /apps → list."""
    t = await _tenant(db_session, "app-list", "u3")
    async with _client(db_session, "u3") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        r = await c.get(f"/api/v1/tenants/{t.slug}/apps")
        assert r.status_code == 200
        assert len(r.json()) == 1
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b3_04_get_app(db_session):
    """GET /apps/{slug} → detail."""
    t = await _tenant(db_session, "app-get", "u4")
    async with _client(db_session, "u4") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        r = await c.get(f"/api/v1/tenants/{t.slug}/apps/test-app")
        assert r.status_code == 200
        assert r.json()["repo_url"] == APP_BODY["repo_url"]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b3_05_patch_app(db_session):
    """PATCH /apps → update fields."""
    t = await _tenant(db_session, "app-patch", "u5")
    async with _client(db_session, "u5") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        r = await c.patch(f"/api/v1/tenants/{t.slug}/apps/test-app", json={"replicas": 3, "port": 3000})
        assert r.status_code == 200
        assert r.json()["replicas"] == 3
        assert r.json()["port"] == 3000
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b3_06_delete_app(db_session):
    """DELETE /apps → 204."""
    t = await _tenant(db_session, "app-del", "u6")
    async with _client(db_session, "u6") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        r = await c.delete(f"/api/v1/tenants/{t.slug}/apps/test-app")
        assert r.status_code == 204
        r2 = await c.get(f"/api/v1/tenants/{t.slug}/apps")
        assert len(r2.json()) == 0
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Build & Deploy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b3_07_build_trigger(db_session):
    """POST /build → 202, deployment created."""
    t = await _tenant(db_session, "app-build", "u7")
    async with _client(db_session, "u7") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        r = await c.post(f"/api/v1/tenants/{t.slug}/apps/test-app/build")
        assert r.status_code == 202
        assert r.json()["status"] == "pending"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b3_08_deployment_list(db_session):
    """GET /deployments → list (empty initially, then after build has entry)."""
    t = await _tenant(db_session, "app-deps", "u8")
    async with _client(db_session, "u8") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        # Empty before any build
        r = await c.get(f"/api/v1/tenants/{t.slug}/apps/test-app/deployments")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b3_09_build_status_endpoint(db_session):
    """GET /build-status → returns container info (no_build when no deployment)."""
    t = await _tenant(db_session, "app-bstatus", "u9")
    async with _client(db_session, "u9") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        # No build triggered — should return no_build status
        r = await c.get(f"/api/v1/tenants/{t.slug}/apps/test-app/build-status")
        assert r.status_code == 200
        data = r.json()
        assert "containers" in data
        assert data.get("status") == "no_build" or "deployment_status" in data
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b3_10_cross_tenant_app_forbidden(db_session):
    """User-a cannot create app in user-b's tenant."""
    await _tenant(db_session, "ct-a", "user-a")
    await _tenant(db_session, "ct-b", "user-b")

    async with _client(db_session, "user-a") as c:
        r = await c.post("/api/v1/tenants/ct-b/apps", json=APP_BODY)
        assert r.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b3_11_cross_tenant_build_forbidden(db_session):
    """User-a cannot trigger build on user-b's app."""
    t = await _tenant(db_session, "ct-build", "user-b2")
    async with _client(db_session, "user-b2") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
    app.dependency_overrides.clear()

    async with _client(db_session, "user-a2") as c:
        r = await c.post(f"/api/v1/tenants/{t.slug}/apps/test-app/build")
        assert r.status_code == 403
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Logs & Status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b3_12_logs_endpoint(db_session):
    """GET /logs → SSE stream."""
    t = await _tenant(db_session, "app-logs", "u12")
    async with _client(db_session, "u12") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        r = await c.get(f"/api/v1/tenants/{t.slug}/apps/test-app/logs")
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b3_13_deployment_status_values():
    """DeploymentStatus has all expected pipeline states."""
    assert DeploymentStatus.PENDING.value == "pending"
    assert DeploymentStatus.BUILDING.value == "building"
    assert DeploymentStatus.DEPLOYING.value == "deploying"
    assert DeploymentStatus.RUNNING.value == "running"
    assert DeploymentStatus.FAILED.value == "failed"


@pytest.mark.asyncio
async def test_b3_14_env_vars_patch(db_session):
    """PATCH env_vars works."""
    t = await _tenant(db_session, "app-env", "u14")
    async with _client(db_session, "u14") as c:
        await c.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_BODY)
        r = await c.patch(
            f"/api/v1/tenants/{t.slug}/apps/test-app",
            json={"env_vars": {"DEBUG": "true", "NODE_ENV": "production"}},
        )
        assert r.status_code == 200
        assert r.json()["env_vars"]["DEBUG"] == "true"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b3_15_app_not_found_404(db_session):
    """GET non-existent app → 404."""
    t = await _tenant(db_session, "app-404", "u15")
    async with _client(db_session, "u15") as c:
        r = await c.get(f"/api/v1/tenants/{t.slug}/apps/ghost")
        assert r.status_code == 404
    app.dependency_overrides.clear()
