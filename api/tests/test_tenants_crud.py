"""Tests for tenants CRUD endpoints (Sprint H3).

Covers: create, list, get, /me, PATCH, delete, cascade.
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


@pytest_asyncio.fixture
async def tc(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_k8s] = _mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "user-1", "email": "u@t.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_tenant(tc):
    resp = await tc.post("/api/v1/tenants", json={"name": "Test", "slug": "tc-create"})
    assert resp.status_code == 201
    assert resp.json()["slug"] == "tc-create"
    assert resp.json()["namespace"] == "tenant-tc-create"


@pytest.mark.asyncio
async def test_create_duplicate_tenant_409(tc):
    await tc.post("/api/v1/tenants", json={"name": "A", "slug": "tc-dup"})
    resp = await tc.post("/api/v1/tenants", json={"name": "B", "slug": "tc-dup"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_tenants(tc):
    await tc.post("/api/v1/tenants", json={"name": "A", "slug": "tc-list-a"})
    await tc.post("/api/v1/tenants", json={"name": "B", "slug": "tc-list-b"})
    resp = await tc.get("/api/v1/tenants")
    assert resp.status_code == 200
    slugs = {t["slug"] for t in resp.json()}
    assert "tc-list-a" in slugs
    assert "tc-list-b" in slugs


@pytest.mark.asyncio
async def test_get_tenant(tc):
    await tc.post("/api/v1/tenants", json={"name": "Get", "slug": "tc-get"})
    resp = await tc.get("/api/v1/tenants/tc-get")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "tc-get"


@pytest.mark.asyncio
async def test_get_tenant_404(tc):
    resp = await tc.get("/api/v1/tenants/ghost")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tenants_me_empty(tc):
    resp = await tc.get("/api/v1/tenants/me")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_tenants_me_with_membership(tc, db_session):
    t = Tenant(
        id=uuid.uuid4(),
        slug="tc-me",
        name="Me",
        namespace="tenant-tc-me",
        keycloak_realm="tc-me",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db_session.add(t)
    await db_session.commit()
    m = TenantMember(
        id=uuid.uuid4(),
        tenant_id=t.id,
        user_id="user-1",
        email="u@t.nl",
        role=MemberRole("owner"),
    )
    db_session.add(m)
    await db_session.commit()

    resp = await tc.get("/api/v1/tenants/me")
    assert len(resp.json()) == 1
    assert resp.json()[0]["slug"] == "tc-me"


@pytest.mark.asyncio
async def test_delete_tenant(tc):
    await tc.post("/api/v1/tenants", json={"name": "Del", "slug": "tc-del"})
    resp = await tc.delete("/api/v1/tenants/tc-del")
    assert resp.status_code == 204

    resp = await tc.get("/api/v1/tenants/tc-del")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_tenant_404(tc):
    resp = await tc.delete("/api/v1/tenants/ghost")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_tenant_db_removed_even_when_external_cleanup_fails(tc, monkeypatch):
    """If TenantService.deprovision raises (ArgoCD/K8s issue), the DB record
    must STILL be deleted. Stuck DB tenants cause '409 already exists' on
    re-create and are worse than orphaned external resources."""
    from app.services import tenant_service as ts_mod

    await tc.post("/api/v1/tenants", json={"name": "Stuck", "slug": "tc-stuck"})

    # Make TenantService.deprovision raise — simulates ArgoCD timeout
    async def boom(self, *args, **kwargs):
        raise RuntimeError("simulated ArgoCD outage")

    monkeypatch.setattr(ts_mod.TenantService, "deprovision", boom)

    resp = await tc.delete("/api/v1/tenants/tc-stuck")
    assert resp.status_code == 204, f"Delete should succeed: {resp.text}"

    # Verify DB record is gone
    resp = await tc.get("/api/v1/tenants/tc-stuck")
    assert resp.status_code == 404, "Tenant must be removed from DB even on cleanup failure"


@pytest.mark.asyncio
async def test_delete_tenant_db_removed_even_when_gitops_fails(tc, monkeypatch):
    """GitOps cleanup failure should not block DB delete."""
    from app.services import gitops_scaffold

    await tc.post("/api/v1/tenants", json={"name": "Stuck2", "slug": "tc-stuck2"})

    async def boom(self, slug):
        raise RuntimeError("simulated Gitea outage")

    monkeypatch.setattr(gitops_scaffold.gitops_scaffold.__class__, "delete_tenant", boom)

    resp = await tc.delete("/api/v1/tenants/tc-stuck2")
    assert resp.status_code == 204

    resp = await tc.get("/api/v1/tenants/tc-stuck2")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# H3f: tenant deprovision orphan Everest sweep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_tenant_calls_orphan_sweep(tc, monkeypatch):
    """delete_tenant must call ManagedServiceProvisioner.cleanup_orphans_by_prefix
    after the normal deprovision loop, with the tenant slug as the prefix.

    This is the second line of defense against orphan Everest DBs left
    behind by out-of-band ManagedService row deletions. See the
    cleanup_orphans_by_prefix() docstring for context.
    """
    from app.services import managed_service as ms_mod

    await tc.post("/api/v1/tenants", json={"name": "Sweep", "slug": "tc-sweep"})

    sweep_called_with: list[str] = []

    async def fake_sweep(self, slug: str) -> list[str]:
        sweep_called_with.append(slug)
        return ["tc-sweep-app-pg"]

    monkeypatch.setattr(
        ms_mod.ManagedServiceProvisioner,
        "cleanup_orphans_by_prefix",
        fake_sweep,
    )

    resp = await tc.delete("/api/v1/tenants/tc-sweep")
    assert resp.status_code == 204, f"delete should succeed: {resp.text}"

    assert sweep_called_with == ["tc-sweep"], "cleanup_orphans_by_prefix must be called once with the tenant slug"

    # DB row gone
    resp = await tc.get("/api/v1/tenants/tc-sweep")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_tenant_continues_if_orphan_sweep_raises(tc, monkeypatch):
    """If the defensive sweep raises, the rest of the cleanup chain MUST continue.
    The DB delete still runs. Best-effort guarantee.
    """
    from app.services import managed_service as ms_mod

    await tc.post("/api/v1/tenants", json={"name": "SweepFail", "slug": "tc-sweep-fail"})

    async def boom(self, slug: str) -> list[str]:
        raise RuntimeError("simulated everest API outage during sweep")

    monkeypatch.setattr(
        ms_mod.ManagedServiceProvisioner,
        "cleanup_orphans_by_prefix",
        boom,
    )

    resp = await tc.delete("/api/v1/tenants/tc-sweep-fail")
    assert resp.status_code == 204, "Sweep failure must NOT block tenant delete"

    # DB row still removed
    resp = await tc.get("/api/v1/tenants/tc-sweep-fail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# H0-3: github_token PATCH guard
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# H0-4: GET /tenants is now user-scoped (no cross-tenant enumeration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tenants_only_returns_caller_memberships(tc, db_session):
    """GET /tenants must only return tenants the caller is a member of.

    Regression for H0-4: prior to the fix this endpoint returned every tenant
    in the system to any authenticated user, enabling tenant enumeration and
    leaking the customer list of a multi-tenant SaaS.
    """
    # user-1 (the tc fixture's authed user) creates one tenant
    await tc.post("/api/v1/tenants", json={"name": "Mine", "slug": "tc-mine"})

    # Insert a second tenant directly with NO membership for user-1
    other = Tenant(
        id=uuid.uuid4(),
        slug="tc-other-owner",
        name="Other",
        namespace="tenant-tc-other-owner",
        keycloak_realm="tc-other-owner",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        TenantMember(
            id=uuid.uuid4(),
            tenant_id=other.id,
            user_id="some-other-user",
            email="other@example.com",
            role=MemberRole("owner"),
        )
    )
    await db_session.commit()

    resp = await tc.get("/api/v1/tenants")
    assert resp.status_code == 200
    slugs = {t["slug"] for t in resp.json()}
    assert "tc-mine" in slugs
    assert "tc-other-owner" not in slugs, "GET /tenants must not leak tenants the caller is not a member of"


@pytest.mark.asyncio
async def test_patch_tenant_cannot_set_github_token(tc, db_session):
    """PATCH /tenants/{slug} must NOT change github_token even if posted.

    Regression for H0-3: prior to the fix, github_token was in _MUTABLE_FIELDS
    in routers/tenants.py, so an admin could paste an arbitrary GitHub token
    (potentially someone else's leaked one) and bypass the OAuth handshake.

    The token must only be set via the OAuth callback in routers/github.py.
    """
    # Create a tenant with a known github_token (simulating a prior OAuth connect)
    await tc.post("/api/v1/tenants", json={"name": "Tok", "slug": "tc-tok"})

    from sqlalchemy import select

    from app.models.tenant import Tenant as TenantModel

    res = await db_session.execute(select(TenantModel).where(TenantModel.slug == "tc-tok"))
    tenant = res.scalar_one()
    tenant.github_token = "ghp_legit_owner_token"
    await db_session.commit()

    # Attacker PATCHes the tenant trying to overwrite the token
    resp = await tc.patch(
        "/api/v1/tenants/tc-tok",
        json={"name": "Tok renamed", "github_token": "ghp_ATTACKER"},
    )
    assert resp.status_code == 200
    # Name change is allowed
    assert resp.json()["name"] == "Tok renamed"

    # github_token MUST be unchanged
    await db_session.refresh(tenant)
    assert tenant.github_token == "ghp_legit_owner_token", (
        "github_token must not be mutable via PATCH — only OAuth callback can set it"
    )
