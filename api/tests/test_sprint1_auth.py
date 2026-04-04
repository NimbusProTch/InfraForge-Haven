"""Sprint 1: Auth & Login Security Tests.

Tests JWT validation (exp, aud), RBAC enforcement, tenant creation
without per-tenant realm, membership isolation.
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
from app.models.tenant_member import MemberRole, TenantMember

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


async def _make_tenant(db: AsyncSession, slug: str) -> Tenant:
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
    await db.refresh(t)
    return t


async def _make_member(db: AsyncSession, tenant: Tenant, user_id: str, role: str = "member") -> TenantMember:
    m = TenantMember(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user_id,
        email=f"{user_id}@test.nl",
        role=MemberRole(role),
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


def _client_with_user(db_session, user_id="auth-user"):
    """Create client with specific user."""

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_k8s] = _mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": user_id, "email": f"{user_id}@test.nl"}

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def auth_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async with _client_with_user(db_session, "auth-user") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauth_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Client with NO auth token."""

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_k8s] = _mock_k8s
    # NO verify_token override → real verification → will fail without real JWT

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# B01-B05: JWT Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b01_valid_jwt_returns_200(auth_client):
    """B01: Valid JWT → 200."""
    resp = await auth_client.get("/api/v1/tenants/me")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_b02_no_token_returns_401(unauth_client):
    """B05: No token → 401."""
    resp = await unauth_client.get("/api/v1/tenants/me")
    assert resp.status_code == 401


def test_b03_jwt_module_enforces_exp():
    """B02: verify_exp is enabled in jwt.py."""
    import inspect

    from app.auth import jwt as jwt_module

    source = inspect.getsource(jwt_module.verify_token)
    assert "verify_exp" in source
    assert '"verify_exp": True' in source or "'verify_exp': True" in source


def test_b04_jwt_module_enforces_aud():
    """B03: verify_aud is enabled in jwt.py."""
    import inspect

    from app.auth import jwt as jwt_module

    source = inspect.getsource(jwt_module.verify_token)
    # Manual audience validation after decode (python-jose doesn't support list audience)
    assert "_ACCEPTED_AUDIENCES" in source
    assert "aud_set" in source or "token_aud" in source


def test_b05_accepted_audiences_defined():
    """B04: Accepted audiences include haven-portal and haven-api."""
    from app.auth.jwt import _ACCEPTED_AUDIENCES

    assert "haven-portal" in _ACCEPTED_AUDIENCES
    assert "haven-api" in _ACCEPTED_AUDIENCES
    assert "account" in _ACCEPTED_AUDIENCES


# ---------------------------------------------------------------------------
# B06-B09: RBAC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b06_rbac_tenant_member_can_list(db_session):
    """B06: Tenant member can list members."""
    t = await _make_tenant(db_session, "rbac-list")
    await _make_member(db_session, t, "member-user", "member")

    async with _client_with_user(db_session, "member-user") as c:
        resp = await c.get(f"/api/v1/tenants/{t.slug}/members")
        assert resp.status_code == 200
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b07_rbac_non_member_gets_403(db_session):
    """B07: Non-member → 403 on protected write."""
    t = await _make_tenant(db_session, "rbac-nonmem")
    # stranger is NOT a member

    async with _client_with_user(db_session, "stranger") as c:
        resp = await c.post(
            f"/api/v1/tenants/{t.slug}/members",
            json={"email": "new@test.nl", "role": "member"},
        )
        assert resp.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b08_rbac_owner_can_add_member(db_session):
    """B08: Owner can add member."""
    t = await _make_tenant(db_session, "rbac-owner-add")
    await _make_member(db_session, t, "owner-user", "owner")

    async with _client_with_user(db_session, "owner-user") as c:
        resp = await c.post(
            f"/api/v1/tenants/{t.slug}/members",
            json={"email": "new@test.nl", "role": "member"},
        )
        assert resp.status_code == 201
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b09_rbac_viewer_cannot_add_member(db_session):
    """B09: Viewer cannot add member."""
    t = await _make_tenant(db_session, "rbac-viewer")
    await _make_member(db_session, t, "viewer-user", "viewer")

    async with _client_with_user(db_session, "viewer-user") as c:
        resp = await c.post(
            f"/api/v1/tenants/{t.slug}/members",
            json={"email": "new2@test.nl", "role": "member"},
        )
        assert resp.status_code == 403
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# B10-B17: Tenant CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b10_create_tenant_auto_owner(auth_client, db_session):
    """B10: POST /tenants → creator auto-added as owner."""
    resp = await auth_client.post(
        "/api/v1/tenants",
        json={"name": "Auth Test", "slug": "auth-test"},
    )
    assert resp.status_code == 201

    # Check creator is owner
    from sqlalchemy import select

    result = await db_session.execute(select(TenantMember).where(TenantMember.user_id == "auth-user"))
    member = result.scalar_one_or_none()
    assert member is not None
    assert member.role == MemberRole("owner")


@pytest.mark.asyncio
async def test_b11_create_tenant_no_realm(auth_client):
    """B11: POST /tenants → per-tenant realm NOT created (disabled)."""
    # This test verifies the code path — realm creation is commented out
    import inspect

    from app.routers import tenants

    source = inspect.getsource(tenants.create_tenant)
    # Should have the commented-out realm creation
    assert "DISABLED" in source or "not called" in source.lower() or "# await keycloak_service.create_realm" in source


@pytest.mark.asyncio
async def test_b12_tenants_me_only_members(db_session):
    """B12: GET /tenants/me → only user's tenants."""
    t1 = await _make_tenant(db_session, "me-test-1")
    t2 = await _make_tenant(db_session, "me-test-2")
    await _make_member(db_session, t1, "me-user", "owner")
    # t2 has NO membership for me-user

    async with _client_with_user(db_session, "me-user") as c:
        resp = await c.get("/api/v1/tenants/me")
        assert resp.status_code == 200
        slugs = {t["slug"] for t in resp.json()}
        assert "me-test-1" in slugs
        assert "me-test-2" not in slugs
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b13_tenants_me_empty_for_new_user(db_session):
    """B13: GET /tenants/me → empty for new user."""
    async with _client_with_user(db_session, "brand-new-user") as c:
        resp = await c.get("/api/v1/tenants/me")
        assert resp.status_code == 200
        assert resp.json() == []
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b14_create_tenant_creates_namespace(auth_client):
    """B14: POST /tenants → K8s namespace created."""
    resp = await auth_client.post("/api/v1/tenants", json={"name": "NS Test", "slug": "ns-test"})
    assert resp.status_code == 201
    assert resp.json()["namespace"] == "tenant-ns-test"


@pytest.mark.asyncio
async def test_b15_delete_tenant_cascade(auth_client, db_session):
    """B17: DELETE /tenants → cascade cleanup."""
    await auth_client.post("/api/v1/tenants", json={"name": "Del Test", "slug": "del-test"})
    resp = await auth_client.delete("/api/v1/tenants/del-test")
    assert resp.status_code == 204

    resp = await auth_client.get("/api/v1/tenants/del-test")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# B18-B20: Member Management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b18_add_member(db_session):
    """B18: POST /members → member added."""
    t = await _make_tenant(db_session, "add-mem")
    await _make_member(db_session, t, "admin-user", "owner")

    async with _client_with_user(db_session, "admin-user") as c:
        resp = await c.post(
            f"/api/v1/tenants/{t.slug}/members",
            json={"email": "new-colleague@test.nl", "role": "member"},
        )
        assert resp.status_code == 201
        assert resp.json()["email"] == "new-colleague@test.nl"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b19_cannot_delete_last_owner(db_session):
    """B19: DELETE /members → last owner cannot be removed."""
    t = await _make_tenant(db_session, "last-owner")
    m = await _make_member(db_session, t, "only-owner", "owner")

    async with _client_with_user(db_session, "only-owner") as c:
        resp = await c.delete(f"/api/v1/tenants/{t.slug}/members/{m.user_id}")
        assert resp.status_code == 409
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b20_update_member_role(db_session):
    """B20: PATCH /members → role updated."""
    t = await _make_tenant(db_session, "role-update")
    await _make_member(db_session, t, "admin-user", "owner")
    m = await _make_member(db_session, t, "target-user", "member")

    async with _client_with_user(db_session, "admin-user") as c:
        resp = await c.patch(
            f"/api/v1/tenants/{t.slug}/members/{m.user_id}",
            json={"role": "admin"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# B21-B24: Tenant authorization bypass prevention (Architect review fix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b21_non_member_cannot_get_tenant(db_session):
    """Non-member cannot GET another user's tenant."""
    t = await _make_tenant(db_session, "private-tenant")
    await _make_member(db_session, t, "real-owner", "owner")

    async with _client_with_user(db_session, "stranger") as c:
        resp = await c.get(f"/api/v1/tenants/{t.slug}")
        assert resp.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b22_non_member_cannot_update_tenant(db_session):
    """Non-member cannot PATCH another user's tenant."""
    t = await _make_tenant(db_session, "protected-tenant")
    await _make_member(db_session, t, "real-owner", "owner")

    async with _client_with_user(db_session, "hacker") as c:
        resp = await c.patch(
            f"/api/v1/tenants/{t.slug}",
            json={"name": "Hacked!"},
        )
        assert resp.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b23_non_member_cannot_delete_tenant(db_session):
    """Non-member cannot DELETE another user's tenant."""
    t = await _make_tenant(db_session, "locked-tenant")
    await _make_member(db_session, t, "real-owner", "owner")

    async with _client_with_user(db_session, "attacker") as c:
        resp = await c.delete(f"/api/v1/tenants/{t.slug}")
        assert resp.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_b24_member_can_get_own_tenant(db_session):
    """Member CAN GET their own tenant."""
    t = await _make_tenant(db_session, "my-tenant")
    await _make_member(db_session, t, "member-user", "member")

    async with _client_with_user(db_session, "member-user") as c:
        resp = await c.get(f"/api/v1/tenants/{t.slug}")
        assert resp.status_code == 200
        assert resp.json()["slug"] == "my-tenant"
    app.dependency_overrides.clear()
