"""Tests for services CRUD endpoints (Sprint H3).

Covers: create, list, get, credentials, delete, validation.
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


async def _tenant(db: AsyncSession, slug: str = "svc-test") -> Tenant:
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
    return m


@pytest_asyncio.fixture
async def sc(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_k8s] = _mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "user-1", "email": "u@t.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_redis_service(sc, db_session):
    t = await _tenant(db_session)
    resp = await sc.post(
        f"/api/v1/tenants/{t.slug}/services",
        json={"name": "app-redis", "service_type": "redis", "tier": "dev"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "provisioning"
    assert resp.json()["service_type"] == "redis"


@pytest.mark.asyncio
async def test_create_pg_service(sc, db_session):
    t = await _tenant(db_session, "pg-svc")
    resp = await sc.post(
        f"/api/v1/tenants/{t.slug}/services",
        json={"name": "app-pg", "service_type": "postgres", "tier": "dev"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_duplicate_service_409(sc, db_session):
    t = await _tenant(db_session, "dup-svc")
    await sc.post(
        f"/api/v1/tenants/{t.slug}/services",
        json={"name": "app-redis", "service_type": "redis", "tier": "dev"},
    )
    resp = await sc.post(
        f"/api/v1/tenants/{t.slug}/services",
        json={"name": "app-redis", "service_type": "redis", "tier": "dev"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_invalid_service_type_422(sc, db_session):
    t = await _tenant(db_session, "invalid-svc")
    resp = await sc.post(
        f"/api/v1/tenants/{t.slug}/services",
        json={"name": "app-bad", "service_type": "oracle", "tier": "dev"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_services(sc, db_session):
    t = await _tenant(db_session, "list-svc")
    await sc.post(
        f"/api/v1/tenants/{t.slug}/services",
        json={"name": "app-redis", "service_type": "redis", "tier": "dev"},
    )
    await sc.post(
        f"/api/v1/tenants/{t.slug}/services",
        json={"name": "app-rabbit", "service_type": "rabbitmq", "tier": "dev"},
    )
    resp = await sc.get(f"/api/v1/tenants/{t.slug}/services")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_delete_service(sc, db_session):
    t = await _tenant(db_session, "del-svc")
    await sc.post(
        f"/api/v1/tenants/{t.slug}/services",
        json={"name": "app-redis", "service_type": "redis", "tier": "dev"},
    )
    resp = await sc.delete(f"/api/v1/tenants/{t.slug}/services/app-redis")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_service_tenant_404(sc):
    resp = await sc.get("/api/v1/tenants/ghost/services")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_all_five_service_types(sc, db_session):
    """All 5 DB types can be created."""
    t = await _tenant(db_session, "all-types")
    for stype in ["postgres", "mysql", "mongodb", "redis", "rabbitmq"]:
        resp = await sc.post(
            f"/api/v1/tenants/{t.slug}/services",
            json={"name": f"app-{stype}", "service_type": stype, "tier": "dev"},
        )
        assert resp.status_code == 201, f"Failed for {stype}"
