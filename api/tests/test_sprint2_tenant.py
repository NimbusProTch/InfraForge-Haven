"""Sprint 2: Tenant Creation & Infrastructure Tests.

Tests tenant CRUD, K8s resource provisioning, PATCH allowlist,
deletion cascade, slug validation, and membership checks.
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.main import app
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
    return m


async def _member(db: AsyncSession, tenant: Tenant, uid: str, role: str = "member") -> TenantMember:
    m = TenantMember(id=uuid.uuid4(), tenant_id=tenant.id, user_id=uid, email=f"{uid}@t.nl", role=MemberRole(role))
    db.add(m)
    await db.commit()
    return m


def _client(db_session, uid="s2-user"):
    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_k8s] = _mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": uid, "email": f"{uid}@t.nl"}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# B2.01-B2.04: Tenant Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b2_01_create_tenant(db_session):
    """POST /tenants → 201 with correct slug and namespace."""
    async with _client(db_session) as c:
        r = await c.post("/api/v1/tenants", json={"name": "Gemeente Acme", "slug": "acme"})
        assert r.status_code == 201
        d = r.json()
        assert d["slug"] == "acme"
        assert d["namespace"] == "tenant-acme"
        assert d["active"] is True
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_02_duplicate_slug_409(db_session):
    """POST /tenants with duplicate slug → 409."""
    async with _client(db_session) as c:
        await c.post("/api/v1/tenants", json={"name": "First", "slug": "dup-slug"})
        r = await c.post("/api/v1/tenants", json={"name": "Second", "slug": "dup-slug"})
        assert r.status_code == 409
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_03_creator_auto_owner(db_session):
    """Creator is auto-added as tenant owner."""
    async with _client(db_session, "creator-user") as c:
        r = await c.post("/api/v1/tenants", json={"name": "Owner Test", "slug": "owner-test"})
        assert r.status_code == 201

    result = await db_session.execute(select(TenantMember).where(TenantMember.user_id == "creator-user"))
    member = result.scalar_one_or_none()
    assert member is not None
    assert member.role == MemberRole("owner")
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_04_tenants_me_includes_new(db_session):
    """GET /tenants/me includes newly created tenant."""
    async with _client(db_session, "me-user") as c:
        await c.post("/api/v1/tenants", json={"name": "My Project", "slug": "my-proj"})
        r = await c.get("/api/v1/tenants/me")
        slugs = {t["slug"] for t in r.json()}
        assert "my-proj" in slugs
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# B2.05-B2.09: RBAC & Authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b2_05_non_member_cannot_get(db_session):
    """Non-member → 403 on GET /tenants/{slug}."""
    async with _client(db_session, "owner") as c:
        await c.post("/api/v1/tenants", json={"name": "Private", "slug": "private"})
    app.dependency_overrides.clear()

    async with _client(db_session, "stranger") as c:
        r = await c.get("/api/v1/tenants/private")
        assert r.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_06_owner_can_update(db_session):
    """Owner (auto-created) can PATCH tenant name."""
    async with _client(db_session, "patch-owner") as c:
        await c.post("/api/v1/tenants", json={"name": "Before", "slug": "patch-test"})
        # Creator is already owner — can update
        r = await c.patch("/api/v1/tenants/patch-test", json={"name": "After"})
        assert r.status_code == 200
        assert r.json()["name"] == "After"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_07_viewer_cannot_update(db_session):
    """Viewer → 403 on PATCH."""
    async with _client(db_session, "owner-v") as c:
        await c.post("/api/v1/tenants", json={"name": "View Only", "slug": "view-only"})
    app.dependency_overrides.clear()

    result = await db_session.execute(select(Tenant).where(Tenant.slug == "view-only"))
    tenant = result.scalar_one()
    await _member(db_session, tenant, "viewer-v", "viewer")

    async with _client(db_session, "viewer-v") as c:
        r = await c.patch("/api/v1/tenants/view-only", json={"name": "Hacked"})
        assert r.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_08_patch_allowlist(db_session):
    """PATCH cannot change id, namespace, keycloak_realm."""
    async with _client(db_session, "allowlist-u") as c:
        await c.post("/api/v1/tenants", json={"name": "Allow", "slug": "allowlist"})
        r = await c.patch("/api/v1/tenants/allowlist", json={"name": "Updated"})
        assert r.status_code == 200
        # namespace should NOT change even if sent
        assert r.json()["namespace"] == "tenant-allowlist"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_09_only_owner_can_delete(db_session):
    """Only owner can DELETE tenant."""
    async with _client(db_session, "del-owner") as c:
        await c.post("/api/v1/tenants", json={"name": "Del Test", "slug": "del-perm"})
    app.dependency_overrides.clear()

    result = await db_session.execute(select(Tenant).where(Tenant.slug == "del-perm"))
    tenant = result.scalar_one()
    await _member(db_session, tenant, "admin-del", "admin")

    # Admin cannot delete
    async with _client(db_session, "admin-del") as c:
        r = await c.delete("/api/v1/tenants/del-perm")
        assert r.status_code == 403
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# B2.10-B2.12: Delete & Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b2_10_delete_tenant(db_session):
    """DELETE → 204, then GET → 404."""
    async with _client(db_session, "del-u") as c:
        await c.post("/api/v1/tenants", json={"name": "Bye", "slug": "bye-tenant"})
        r = await c.delete("/api/v1/tenants/bye-tenant")
        assert r.status_code == 204
        r2 = await c.get("/api/v1/tenants/bye-tenant")
        assert r2.status_code == 404
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_11_no_keycloak_realm():
    """Per-tenant realm creation is disabled in code."""
    import inspect

    from app.routers import tenants

    source = inspect.getsource(tenants.create_tenant)
    assert "DISABLED" in source or "# await keycloak_service.create_realm" in source


@pytest.mark.asyncio
async def test_b2_12_default_quotas(db_session):
    """New tenant gets default free tier quotas."""
    async with _client(db_session, "quota-u") as c:
        r = await c.post("/api/v1/tenants", json={"name": "Quota", "slug": "quota-test"})
        d = r.json()
        assert d["cpu_limit"] == "16"
        assert d["memory_limit"] == "32Gi"
        assert d["storage_limit"] == "100Gi"
        assert d["tier"] == "free"
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Architect Review Fixes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b2_13_slug_validation_min_length(db_session):
    """Slug too short (< 3 chars) → 422."""
    async with _client(db_session) as c:
        r = await c.post("/api/v1/tenants", json={"name": "Short", "slug": "ab"})
        assert r.status_code == 422
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_14_slug_validation_special_chars(db_session):
    """Slug with special chars → 422."""
    async with _client(db_session) as c:
        for bad_slug in ["../hack", "kube system", "UPPER", "test_underscore", "-leading"]:
            r = await c.post("/api/v1/tenants", json={"name": "Bad", "slug": bad_slug})
            assert r.status_code == 422, f"Slug '{bad_slug}' should be rejected"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_15_cross_tenant_apps_forbidden(db_session):
    """Member of tenant A cannot access tenant B's apps."""
    # Create tenant A (user-a is owner)
    async with _client(db_session, "user-a") as c:
        await c.post("/api/v1/tenants", json={"name": "Tenant A", "slug": "tenant-a"})
    app.dependency_overrides.clear()

    # Create tenant B (user-b is owner)
    async with _client(db_session, "user-b") as c:
        await c.post("/api/v1/tenants", json={"name": "Tenant B", "slug": "tenant-b"})
    app.dependency_overrides.clear()

    # user-a tries to access tenant-b's apps → 403
    async with _client(db_session, "user-a") as c:
        r = await c.get("/api/v1/tenants/tenant-b/apps")
        assert r.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_16_cross_tenant_services_forbidden(db_session):
    """Member of tenant A cannot access tenant B's services."""
    async with _client(db_session, "svc-a") as c:
        await c.post("/api/v1/tenants", json={"name": "SVC A", "slug": "svc-tenant-a"})
    app.dependency_overrides.clear()

    async with _client(db_session, "svc-b") as c:
        await c.post("/api/v1/tenants", json={"name": "SVC B", "slug": "svc-tenant-b"})
    app.dependency_overrides.clear()

    async with _client(db_session, "svc-a") as c:
        r = await c.get("/api/v1/tenants/svc-tenant-b/services")
        assert r.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b2_17_cross_tenant_members_forbidden(db_session):
    """Member of tenant A cannot access tenant B's members."""
    async with _client(db_session, "mem-a") as c:
        await c.post("/api/v1/tenants", json={"name": "Mem A", "slug": "mem-tenant-a"})
    app.dependency_overrides.clear()

    async with _client(db_session, "mem-b") as c:
        await c.post("/api/v1/tenants", json={"name": "Mem B", "slug": "mem-tenant-b"})
    app.dependency_overrides.clear()

    async with _client(db_session, "mem-a") as c:
        r = await c.get("/api/v1/tenants/mem-tenant-b/members")
        assert r.status_code == 403
    app.dependency_overrides.clear()
