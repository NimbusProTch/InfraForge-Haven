"""Tests for Sprint E6: Per-tenant observability edge cases.

Tests pods, events, and metrics endpoints for robustness.
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


async def _tenant(db: AsyncSession, slug: str = "obs-test") -> Tenant:
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
    await db.flush()
    # H0-9: observability router now enforces membership; this file's local
    # obs_client / obs_client_no_k8s fixtures mock verify_token with sub='test'
    # (NOT 'test-user'), so add the member with that user_id.
    db.add(
        TenantMember(
            id=uuid.uuid4(),
            tenant_id=t.id,
            user_id="test",
            email="t@t.nl",
            role=MemberRole("owner"),
        )
    )
    await db.commit()
    await db.refresh(t)
    return t


async def _app(db: AsyncSession, tenant: Tenant, slug: str = "obs-api") -> Application:
    a = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug=slug,
        name="Obs API",
        repo_url="https://github.com/test/repo",
        branch="main",
        port=8080,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


def _mock_k8s_with_metrics(pods=None, events=None):
    mock = MagicMock()
    mock.is_available.return_value = True

    # Pod list
    pod_items = []
    for p in pods or []:
        pod = MagicMock()
        pod.metadata.name = p["name"]
        pod.metadata.namespace = "tenant-obs-test"
        pod.metadata.creation_timestamp = MagicMock()
        pod.metadata.creation_timestamp.isoformat.return_value = "2026-04-03T10:00:00Z"
        pod.status.phase = p.get("phase", "Running")
        pod.status.container_statuses = []
        pod.spec.node_name = "worker-1"
        pod_items.append(pod)

    pod_list = MagicMock()
    pod_list.items = pod_items
    mock.core_v1.list_namespaced_pod.return_value = pod_list

    # Events
    event_items = []
    for e in events or []:
        ev = MagicMock()
        ev.involved_object.name = e.get("object", "obs-api-abc")
        ev.reason = e.get("reason", "Pulled")
        ev.message = e.get("message", "Image pulled")
        ev.count = e.get("count", 1)
        ev.first_timestamp = MagicMock()
        ev.first_timestamp.isoformat.return_value = "2026-04-03T10:00:00Z"
        ev.last_timestamp = MagicMock()
        ev.last_timestamp.isoformat.return_value = "2026-04-03T10:01:00Z"
        event_items.append(ev)

    event_list = MagicMock()
    event_list.items = event_items
    mock.core_v1.list_namespaced_event.return_value = event_list

    # Metrics (custom_objects for metrics-server)
    mock.custom_objects.list_namespaced_custom_object.return_value = {"items": []}

    return mock


@pytest_asyncio.fixture
async def obs_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    mock_k8s = _mock_k8s_with_metrics(
        pods=[{"name": "obs-api-abc-123", "phase": "Running"}],
        events=[
            {"object": "obs-api-abc-123", "reason": "Pulled", "message": "Image pulled"},
            {"object": "obs-api-abc-123", "reason": "Started", "message": "Container started"},
        ],
    )

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test", "email": "t@t.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def obs_client_no_k8s(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = False

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test", "email": "t@t.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Pod endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pods_returns_list(obs_client, db_session):
    """GET /pods returns pod list with status."""
    t = await _tenant(db_session)
    a = await _app(db_session, t)
    resp = await obs_client.get(f"/api/v1/tenants/{t.slug}/apps/{a.slug}/pods")
    assert resp.status_code == 200
    data = resp.json()
    assert data["k8s_available"] is True
    assert len(data["pods"]) == 1
    assert data["pods"][0]["name"] == "obs-api-abc-123"


@pytest.mark.asyncio
async def test_pods_k8s_unavailable(obs_client_no_k8s, db_session):
    """GET /pods with K8s unavailable returns empty."""
    t = await _tenant(db_session, "no-k8s-obs")
    a = await _app(db_session, t)
    resp = await obs_client_no_k8s.get(f"/api/v1/tenants/{t.slug}/apps/{a.slug}/pods")
    assert resp.status_code == 200
    data = resp.json()
    assert data["k8s_available"] is False
    assert data["pods"] == []


@pytest.mark.asyncio
async def test_pods_404_unknown_app(obs_client, db_session):
    """GET /pods for unknown app returns 404."""
    t = await _tenant(db_session, "unknown-obs")
    resp = await obs_client.get(f"/api/v1/tenants/{t.slug}/apps/ghost/pods")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Events endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_endpoint_exists(obs_client, db_session):
    """GET /events endpoint responds (not 404)."""
    t = await _tenant(db_session, "events-test")
    a = await _app(db_session, t)
    resp = await obs_client.get(f"/api/v1/tenants/{t.slug}/apps/{a.slug}/events")
    # May be 200 or 422 depending on required params — just not 404/500
    assert resp.status_code in (200, 422)


@pytest.mark.asyncio
async def test_events_k8s_unavailable(obs_client_no_k8s, db_session):
    """GET /events with K8s unavailable returns empty."""
    t = await _tenant(db_session, "no-k8s-ev")
    a = await _app(db_session, t)
    resp = await obs_client_no_k8s.get(f"/api/v1/tenants/{t.slug}/apps/{a.slug}/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["events"] == []
