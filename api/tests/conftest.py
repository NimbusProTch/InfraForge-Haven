"""Pytest fixtures for Haven Platform API tests."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.k8s.client import K8sClient
from app.main import app
from app.models.application import Application
from app.models.base import Base
from app.models.cluster import Cluster  # noqa: F401 — ensures table created
from app.models.cronjob import CronJob  # noqa: F401 — registers table in metadata
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember  # noqa: F401 — ensures table created

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Global patch: prevent real run_pipeline from creating unawaited coroutines
# in webhook tests. Each test that needs to verify pipeline behaviour can
# re-patch locally.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_pipeline_globally():
    """Patch run_pipeline with a plain MagicMock so asyncio.create_task receives
    a non-coroutine value and no unawaited-coroutine RuntimeWarnings are raised."""
    with patch("app.routers.webhooks.run_pipeline", MagicMock(return_value=None)):
        yield


# ---------------------------------------------------------------------------
# DB fixtures (function-scoped to avoid anyio scope conflicts)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh in-memory SQLite session per test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Mock K8s client
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_k8s() -> K8sClient:
    """A K8sClient with all sub-clients mocked out."""
    k8s = MagicMock(spec=K8sClient)
    k8s.is_available.return_value = False
    k8s.core_v1 = MagicMock()
    k8s.apps_v1 = MagicMock()
    k8s.batch_v1 = MagicMock()
    k8s.autoscaling_v2 = MagicMock()
    k8s.custom_objects = MagicMock()
    return k8s


@pytest.fixture
def mock_k8s_available() -> MagicMock:
    """K8s client that reports as available with a mock CustomObjectsApi."""
    k8s = MagicMock()
    k8s.is_available.return_value = True
    k8s.custom_objects = MagicMock()
    k8s.custom_objects.create_namespaced_custom_object.return_value = {}
    k8s.custom_objects.delete_namespaced_custom_object.return_value = {}
    k8s.custom_objects.get_namespaced_custom_object.return_value = {
        "status": {"readyInstances": 1, "phase": "Cluster in healthy state"},
        "spec": {"instances": 1},
    }
    return k8s


@pytest.fixture
def mock_k8s_unavailable() -> MagicMock:
    """K8s client that reports as unavailable."""
    k8s = MagicMock()
    k8s.is_available.return_value = False
    k8s.custom_objects = None
    return k8s


# ---------------------------------------------------------------------------
# Async test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession, mock_k8s: K8sClient) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTPX client with DB and K8s overrides."""

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test-user", "email": "test@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sample_tenant(db_session: AsyncSession) -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="test-gemeente",
        name="Test Gemeente",
        namespace="tenant-test-gemeente",
        keycloak_realm="test-gemeente",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def tenant_with_app(db_session: AsyncSession):
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="obs-tenant",
        name="Obs Tenant",
        namespace="tenant-obs-tenant",
        keycloak_realm="obs-tenant",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db_session.add(tenant)
    await db_session.flush()

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="my-app",
        name="My App",
        repo_url="https://github.com/org/repo",
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
