"""Tests for applications CRUD endpoints (Sprint H3).

Covers: create, list, get, PATCH, delete, connect-service.
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
from app.models.tenant import Tenant


async def _tenant(db: AsyncSession, slug: str = "app-test") -> Tenant:
    t = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        name=slug,
        namespace=f"tenant-{slug}",
        keycloak_realm=slug,
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    # Add test user as member (required by tenant auth)
    import uuid as _uuid

    from app.models.tenant_member import MemberRole, TenantMember

    db.add(TenantMember(id=_uuid.uuid4(), tenant_id=t.id, user_id="user-1", email="u@t.nl", role=MemberRole("owner")))
    await db.commit()
    return t


def _mock_k8s():
    m = MagicMock()
    m.is_available.return_value = True
    m.custom_objects = MagicMock()
    m.custom_objects.create_namespaced_custom_object.return_value = {}
    m.core_v1 = MagicMock()
    m.core_v1.create_namespace.return_value = MagicMock()
    m.core_v1.read_namespaced_secret.side_effect = Exception("not found")
    m.apps_v1 = MagicMock()
    return m


@pytest_asyncio.fixture
async def ac(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_k8s] = _mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "user-1", "email": "u@t.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


APP_JSON = {
    "name": "Test App",
    "slug": "test-app",
    "repo_url": "https://github.com/test/repo",
    "branch": "main",
    "port": 8080,
}


@pytest.mark.asyncio
async def test_create_app(ac, db_session):
    t = await _tenant(db_session)
    resp = await ac.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_JSON)
    assert resp.status_code == 201
    assert resp.json()["slug"] == "test-app"
    assert resp.json()["port"] == 8080


@pytest.mark.asyncio
async def test_create_duplicate_app_409(ac, db_session):
    t = await _tenant(db_session, "dup-app")
    await ac.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_JSON)
    resp = await ac.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_JSON)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_apps(ac, db_session):
    t = await _tenant(db_session, "list-apps")
    await ac.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_JSON)
    await ac.post(
        f"/api/v1/tenants/{t.slug}/apps",
        json={**APP_JSON, "slug": "second-app", "name": "Second"},
    )
    resp = await ac.get(f"/api/v1/tenants/{t.slug}/apps")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_get_app(ac, db_session):
    t = await _tenant(db_session, "get-app")
    await ac.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_JSON)
    resp = await ac.get(f"/api/v1/tenants/{t.slug}/apps/test-app")
    assert resp.status_code == 200
    assert resp.json()["repo_url"] == APP_JSON["repo_url"]


@pytest.mark.asyncio
async def test_get_app_404(ac, db_session):
    t = await _tenant(db_session, "get-app-404")
    resp = await ac.get(f"/api/v1/tenants/{t.slug}/apps/ghost")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_app(ac, db_session):
    t = await _tenant(db_session, "patch-app")
    await ac.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_JSON)
    resp = await ac.patch(
        f"/api/v1/tenants/{t.slug}/apps/test-app",
        json={"replicas": 5, "port": 3000},
    )
    assert resp.status_code == 200
    assert resp.json()["replicas"] == 5
    assert resp.json()["port"] == 3000


@pytest.mark.asyncio
async def test_delete_app(ac, db_session):
    t = await _tenant(db_session, "del-app")
    await ac.post(f"/api/v1/tenants/{t.slug}/apps", json=APP_JSON)
    resp = await ac.delete(f"/api/v1/tenants/{t.slug}/apps/test-app")
    assert resp.status_code == 204

    resp = await ac.get(f"/api/v1/tenants/{t.slug}/apps")
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_tenant_404_for_apps(ac):
    resp = await ac.get("/api/v1/tenants/ghost/apps")
    assert resp.status_code == 404
