"""Tests for deployment endpoints, log streaming, and status transitions (Sprint E3).

Tests:
- List deployments
- Get single deployment
- Deployment status transitions (PENDING → BUILDING → DEPLOYING → RUNNING → FAILED)
- Log streaming SSE: multi-replica, build logs, error cases
- Build container names (buildctl, not kaniko)
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.main import app
from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.tenant import Tenant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _make_tenant(db: AsyncSession, slug: str = "deploy-test") -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        name=f"Deploy {slug}",
        namespace=f"tenant-{slug}",
        keycloak_realm=slug,
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def _make_app(db: AsyncSession, tenant: Tenant, slug: str = "test-api") -> Application:
    application = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug=slug,
        name="Test API",
        repo_url="https://github.com/test/repo",
        branch="main",
        port=8080,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


async def _make_deployment(
    db: AsyncSession,
    application: Application,
    status: DeploymentStatus = DeploymentStatus.RUNNING,
    error_message: str | None = None,
    build_job_name: str | None = None,
    image_tag: str | None = None,
) -> Deployment:
    deployment = Deployment(
        id=uuid.uuid4(),
        application_id=application.id,
        commit_sha="abc12345",
        status=status,
        error_message=error_message,
        build_job_name=build_job_name,
        image_tag=image_tag,
    )
    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)
    return deployment


def _mock_k8s_with_pods(pods: list[dict] | None = None) -> MagicMock:
    """Create mock K8s with pod list support."""
    mock = MagicMock()
    mock.is_available.return_value = True
    mock.custom_objects = MagicMock()

    # Build pod objects
    pod_items = []
    for p in (pods or []):
        pod = MagicMock()
        pod.metadata.name = p["name"]
        pod.status.phase = p.get("phase", "Running")
        pod_items.append(pod)

    pod_list = MagicMock()
    pod_list.items = pod_items
    mock.core_v1.list_namespaced_pod.return_value = pod_list
    mock.core_v1.read_namespaced_pod_log.return_value = "2026-04-03 OK\nHealthy"

    return mock


@pytest_asyncio.fixture
async def deploy_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Client with K8s available and mock pods."""
    mock_k8s = _mock_k8s_with_pods([
        {"name": "test-api-abc-111", "phase": "Running"},
        {"name": "test-api-abc-222", "phase": "Running"},
    ])

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test-user", "email": "test@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def deploy_client_no_k8s(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Client with K8s unavailable."""
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = False

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test-user", "email": "test@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# List / Get deployments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_deployments(deploy_client, db_session):
    """GET /deployments returns list of deployments."""
    tenant = await _make_tenant(db_session)
    application = await _make_app(db_session, tenant)
    d1 = await _make_deployment(db_session, application, DeploymentStatus.RUNNING)
    d2 = await _make_deployment(db_session, application, DeploymentStatus.FAILED, error_message="OOM")

    resp = await deploy_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{application.slug}/deployments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_get_single_deployment(deploy_client, db_session):
    """GET /deployments/{id} returns a single deployment."""
    tenant = await _make_tenant(db_session, "single-deploy")
    application = await _make_app(db_session, tenant)
    deployment = await _make_deployment(db_session, application, image_tag="harbor.io/test:abc")

    resp = await deploy_client.get(
        f"/api/v1/tenants/{tenant.slug}/apps/{application.slug}/deployments/{deployment.id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(deployment.id)
    assert data["image_tag"] == "harbor.io/test:abc"
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_get_deployment_404(deploy_client, db_session):
    """GET /deployments/{id} returns 404 for unknown deployment."""
    tenant = await _make_tenant(db_session, "not-found")
    application = await _make_app(db_session, tenant)
    await _make_deployment(db_session, application)

    resp = await deploy_client.get(
        f"/api/v1/tenants/{tenant.slug}/apps/{application.slug}/deployments/{uuid.uuid4()}"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deployment_status_values():
    """DeploymentStatus has all expected values."""
    assert DeploymentStatus.PENDING.value == "pending"
    assert DeploymentStatus.BUILDING.value == "building"
    assert DeploymentStatus.DEPLOYING.value == "deploying"
    assert DeploymentStatus.RUNNING.value == "running"
    assert DeploymentStatus.FAILED.value == "failed"


@pytest.mark.asyncio
async def test_failed_deployment_has_error_message(deploy_client, db_session):
    """Failed deployments include error_message."""
    tenant = await _make_tenant(db_session, "fail-msg")
    application = await _make_app(db_session, tenant)
    deployment = await _make_deployment(
        db_session, application, DeploymentStatus.FAILED, error_message="CrashLoopBackOff: OOMKilled"
    )

    resp = await deploy_client.get(
        f"/api/v1/tenants/{tenant.slug}/apps/{application.slug}/deployments/{deployment.id}"
    )
    data = resp.json()
    assert data["status"] == "failed"
    assert "OOMKilled" in data["error_message"]


# ---------------------------------------------------------------------------
# Log streaming SSE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_streaming_multi_replica(deploy_client, db_session):
    """GET /logs streams logs from multiple pods with prefixes."""
    tenant = await _make_tenant(db_session, "multi-log")
    application = await _make_app(db_session, tenant)
    await _make_deployment(db_session, application, DeploymentStatus.RUNNING)

    resp = await deploy_client.get(
        f"/api/v1/tenants/{tenant.slug}/apps/{application.slug}/logs"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    # Multi-replica: should have pod name prefixes
    assert "[test-api-abc-111]" in body
    assert "[test-api-abc-222]" in body
    assert "[end]" in body


@pytest.mark.asyncio
async def test_log_streaming_single_pod_filter(deploy_client, db_session):
    """GET /logs?pod=name streams from specific pod without prefix."""
    tenant = await _make_tenant(db_session, "single-log")
    application = await _make_app(db_session, tenant)
    await _make_deployment(db_session, application, DeploymentStatus.RUNNING)

    resp = await deploy_client.get(
        f"/api/v1/tenants/{tenant.slug}/apps/{application.slug}/logs?pod=test-api-abc-111"
    )
    body = resp.text
    # Single pod filter: no prefix
    assert "test-api-abc-111" in body
    assert "[test-api-abc-222]" not in body


@pytest.mark.asyncio
async def test_log_streaming_k8s_unavailable(deploy_client_no_k8s, db_session):
    """GET /logs returns message when K8s unavailable."""
    tenant = await _make_tenant(db_session, "nok8s-log")
    application = await _make_app(db_session, tenant)
    await _make_deployment(db_session, application, DeploymentStatus.RUNNING)

    resp = await deploy_client_no_k8s.get(
        f"/api/v1/tenants/{tenant.slug}/apps/{application.slug}/logs"
    )
    body = resp.text
    assert "not available" in body.lower() or "end" in body


@pytest.mark.asyncio
async def test_log_streaming_failed_deployment(deploy_client, db_session):
    """GET /logs shows error message for failed deployments with no pods."""
    mock_k8s = _mock_k8s_with_pods([])  # no pods

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test", "email": "t@t.nl"}

    tenant = await _make_tenant(db_session, "fail-log")
    application = await _make_app(db_session, tenant)
    await _make_deployment(
        db_session, application, DeploymentStatus.FAILED, error_message="ImagePullBackOff: not found"
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/tenants/{tenant.slug}/apps/{application.slug}/logs")
        body = resp.text
        assert "failed" in body.lower()
        assert "ImagePullBackOff" in body

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_log_streaming_building_status(deploy_client, db_session):
    """GET /logs shows build progress for BUILDING status."""
    tenant = await _make_tenant(db_session, "build-log")
    application = await _make_app(db_session, tenant)
    await _make_deployment(
        db_session, application, DeploymentStatus.BUILDING, build_job_name="build-test-api-123"
    )

    resp = await deploy_client.get(
        f"/api/v1/tenants/{tenant.slug}/apps/{application.slug}/logs"
    )
    body = resp.text
    assert "build in progress" in body.lower()
    assert "build-test-api-123" in body


# ---------------------------------------------------------------------------
# Build container name fix
# ---------------------------------------------------------------------------


def test_build_containers_use_buildctl():
    """Build log streaming uses buildctl container name (not kaniko)."""
    import inspect
    from app.routers import deployments

    source = inspect.getsource(deployments.stream_logs)
    assert "buildctl" in source
    assert "kaniko" not in source
