"""H0-9 / H0-10 — Cross-tenant isolation regression sweep.

This single test file walks every router that was found to leak data across
tenant boundaries during the Sprint H0 audit and asserts that a non-member
caller is rejected with 403 on a representative read endpoint.

Each parametrised case carries the H0-N tag and the file:line of the original
gap so a future regression's traceback explains itself.

The test asserts BOTH:
  - The status code (403)
  - The error message ("not a member")

so that an accidental 404/500/200 with the right shape would still fail.
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
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_k8s() -> MagicMock:
    m = MagicMock()
    m.is_available.return_value = False  # Forces graceful K8s-unavailable paths
    m.core_v1 = MagicMock()
    m.apps_v1 = MagicMock()
    m.batch_v1 = MagicMock()
    m.autoscaling_v2 = MagicMock()
    m.custom_objects = MagicMock()
    return m


@pytest_asyncio.fixture
async def isolation_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async client authed as 'attacker' — a user with NO tenant memberships."""

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = _mock_k8s
    app.dependency_overrides[verify_token] = lambda: {
        "sub": "attacker",
        "email": "attacker@evil.example",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def victim_tenant(db_session: AsyncSession) -> tuple[Tenant, Application]:
    """A tenant + app owned by 'victim-user'. The 'attacker' fixture above is NOT a member."""
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="victim-tenant",
        name="Victim Gemeente",
        namespace="tenant-victim-tenant",
        keycloak_realm="victim-tenant",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(
        TenantMember(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            user_id="victim-user",
            email="victim@haven.nl",
            role=MemberRole.owner,
        )
    )
    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="victim-app",
        name="Victim App",
        repo_url="https://github.com/victim/repo",
        branch="main",
        resource_cpu_limit="500m",
        resource_memory_limit="256Mi",
        resource_cpu_request="100m",
        resource_memory_request="64Mi",
    )
    db_session.add(app_obj)
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(app_obj)
    return tenant, app_obj


# ---------------------------------------------------------------------------
# Endpoints to probe — each represents a router whose helper was missing
# the membership check before the H0-9 / H0-10 fixes.
# ---------------------------------------------------------------------------

# (router_id, http_method, path_template, h0_tag)
PROBE_ENDPOINTS: list[tuple[str, str, str, str]] = [
    # H0-9 group: routers that had ZERO membership check
    ("gdpr-consent", "GET", "/api/v1/tenants/{slug}/gdpr/consent", "H0-9"),
    ("gdpr-export", "GET", "/api/v1/tenants/{slug}/gdpr/export", "H0-9"),
    ("gdpr-retention", "GET", "/api/v1/tenants/{slug}/gdpr/retention", "H0-9"),
    ("billing-usage", "GET", "/api/v1/tenants/{slug}/usage", "H0-9"),
    ("pvcs-list", "GET", "/api/v1/tenants/{slug}/apps/{app}/volumes", "H0-9"),
    ("observability-pods", "GET", "/api/v1/tenants/{slug}/apps/{app}/pods", "H0-9"),
    ("environments-list", "GET", "/api/v1/tenants/{slug}/apps/{app}/environments", "H0-9"),
    ("cronjobs-list", "GET", "/api/v1/tenants/{slug}/apps/{app}/cronjobs", "H0-9"),
    ("domains-list", "GET", "/api/v1/tenants/{slug}/apps/{app}/domains", "H0-9"),
    ("canary-status", "GET", "/api/v1/tenants/{slug}/apps/{app}/canary", "H0-9"),
    # H0-10 group: routers whose helper was fail-open (`current_user: dict | None = None`)
    ("services-list", "GET", "/api/v1/tenants/{slug}/services", "H0-10"),
    ("applications-list", "GET", "/api/v1/tenants/{slug}/apps", "H0-10"),
    ("deployments-list", "GET", "/api/v1/tenants/{slug}/apps/{app}/deployments", "H0-10"),
    ("members-list", "GET", "/api/v1/tenants/{slug}/members", "H0-10"),
    # H0-11 group: events.py SSE streams had NO authentication AT ALL — anyone
    # on the network could subscribe to any tenant's lifecycle bus
    ("events-tenant", "GET", "/api/v1/tenants/{slug}/events", "H0-11"),
    ("events-app-lifecycle", "GET", "/api/v1/tenants/{slug}/apps/{app}/lifecycle-events", "H0-11"),
    # H0-12 group: github.py /connect was an RCE vector — any authenticated user
    # could paste an OAuth token onto any tenant, then the next build would
    # clone the attacker repo with attacker credentials inside the victim ns
    ("github-status", "GET", "/api/v1/github/status/{slug}", "H0-12"),
    ("github-disconnect", "DELETE", "/api/v1/github/connect/{slug}", "H0-12"),
]


@pytest.mark.parametrize(
    "router_id,method,path_template,h0_tag",
    PROBE_ENDPOINTS,
    ids=[e[0] for e in PROBE_ENDPOINTS],
)
@pytest.mark.asyncio
async def test_cross_tenant_access_returns_403(
    isolation_client: AsyncClient,
    victim_tenant: tuple[Tenant, Application],
    router_id: str,
    method: str,
    path_template: str,
    h0_tag: str,
) -> None:
    """An authenticated non-member must NOT be able to read victim-tenant data.

    Pre-fix behaviour:
      - H0-9 routers returned 200 with the tenant's actual data
      - H0-10 routers returned 200 because the helper silently allowed `None`

    Post-fix behaviour:
      - All routers must return 403 with detail "not a member"
    """
    tenant, app_obj = victim_tenant
    path = path_template.format(slug=tenant.slug, app=app_obj.slug)
    response = await isolation_client.request(method, path)
    assert response.status_code == 403, (
        f"[{h0_tag}] {router_id}: expected 403, got {response.status_code}. Body: {response.text[:200]}"
    )
    body = response.json()
    detail = (body.get("detail") or "").lower()
    assert "not a member" in detail, f"[{h0_tag}] {router_id}: expected 'not a member' in detail, got {detail!r}"


# ---------------------------------------------------------------------------
# H0-13: Vertical privilege escalation regression
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def viewer_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async client authed as 'viewer-user' — paired with `viewer_tenant`
    fixture below to put the user in the tenant as a viewer (not owner/admin).
    """

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = _mock_k8s
    app.dependency_overrides[verify_token] = lambda: {
        "sub": "viewer-user",
        "email": "viewer@example.com",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def viewer_tenant(db_session: AsyncSession) -> tuple[Tenant, str]:
    """A tenant where the calling user ('viewer-user') is a VIEWER and another
    user ('owner-user') is the owner. Returns (tenant, target_user_id).
    """
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="viewer-tenant",
        name="Viewer Test",
        namespace="tenant-viewer-tenant",
        keycloak_realm="viewer-tenant",
        cpu_limit="2",
        memory_limit="4Gi",
        storage_limit="20Gi",
    )
    db_session.add(tenant)
    await db_session.flush()
    db_session.add(
        TenantMember(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            user_id="owner-user",
            email="owner@example.com",
            role=MemberRole("owner"),
        )
    )
    db_session.add(
        TenantMember(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            user_id="viewer-user",
            email="viewer@example.com",
            role=MemberRole("viewer"),
        )
    )
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant, "owner-user"


@pytest.mark.asyncio
async def test_viewer_cannot_promote_self_to_owner(
    viewer_client: AsyncClient,
    viewer_tenant: tuple[Tenant, str],
) -> None:
    """H0-13: PATCH /members/{user_id} previously had no role check.

    Pre-fix: a viewer could PATCH their own membership row with `{"role": "owner"}`
    and silently take over the tenant. Post-fix: 403 because PATCH carries
    `require_role("owner","admin")`.
    """
    tenant, _ = viewer_tenant
    response = await viewer_client.patch(
        f"/api/v1/tenants/{tenant.slug}/members/viewer-user",
        json={"role": "owner"},
    )
    assert response.status_code == 403, (
        f"viewer must not be able to promote themselves: got {response.status_code} {response.text[:200]}"
    )


@pytest.mark.asyncio
async def test_viewer_cannot_delete_other_member(
    viewer_client: AsyncClient,
    viewer_tenant: tuple[Tenant, str],
) -> None:
    """H0-13: DELETE /members/{user_id} previously had no role check.

    Pre-fix: a viewer could DELETE the owner row (modulo the "last owner"
    guard which only fired when there was exactly one owner — but a viewer
    could still nuke every admin). Post-fix: 403.
    """
    tenant, target = viewer_tenant
    response = await viewer_client.delete(
        f"/api/v1/tenants/{tenant.slug}/members/{target}",
    )
    assert response.status_code == 403, (
        f"viewer must not be able to delete other members: got {response.status_code} {response.text[:200]}"
    )
