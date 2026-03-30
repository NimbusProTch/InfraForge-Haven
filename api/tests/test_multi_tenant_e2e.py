"""Comprehensive multi-tenant E2E backend tests.

Tests the full lifecycle of 3 tenants with different managed services:
  - Rotterdam: PostgreSQL + Redis (create, provision, connect, delete)
  - Amsterdam: MongoDB + Redis (create, provision, connect, delete)
  - Utrecht: MySQL + RabbitMQ (create, provision, connect, delete)

Covers:
  - Tenant CRUD (create, get, list, update, delete)
  - Application CRUD (create, get, list, update, delete)
  - Managed service provisioning (all 5 types: PG, MySQL, MongoDB, Redis, RabbitMQ)
  - Service connect/disconnect to apps
  - Service status sync (Everest + CRD paths)
  - Service credentials endpoint
  - Cross-tenant isolation (services scoped to tenant)
  - Full cleanup: tenant delete cascades services, apps, namespace, AppSet, Harbor
  - Simultaneous tenant operations (parallel creation)
  - ArgoCD ApplicationSet per tenant
  - Harbor project per tenant
  - Keycloak realm per tenant (non-blocking)
  - GitOps scaffold per tenant (non-blocking)
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from kubernetes.client.exceptions import ApiException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.k8s.client import K8sClient
from app.main import app
from app.models.application import Application
from app.models.base import Base
from app.models.cluster import Cluster  # noqa: F401
from app.models.cronjob import CronJob  # noqa: F401
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember  # noqa: F401
from app.services.managed_service import (
    EVEREST_NAMESPACE,
    ManagedServiceProvisioner,
    _CONNECTION_HINT_MAP,
    _EVEREST_SECRET_NAME,
    _SECRET_NAME_MAP,
    _cnpg_cluster_body,
    _mongodb_body,
    _mysql_body,
    _rabbitmq_body,
    _redis_body,
)
from app.services.tenant_service import TenantService

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
def k8s_mock():
    """K8s client with all sub-clients mocked, available=True."""
    k8s = MagicMock(spec=K8sClient)
    k8s.is_available.return_value = True
    k8s.core_v1 = MagicMock()
    k8s.apps_v1 = MagicMock()
    k8s.batch_v1 = MagicMock()
    k8s.rbac_v1 = MagicMock()
    k8s.autoscaling_v2 = MagicMock()
    k8s.custom_objects = MagicMock()
    k8s.custom_objects.create_namespaced_custom_object.return_value = {}
    k8s.custom_objects.delete_namespaced_custom_object.return_value = {}
    k8s.custom_objects.get_namespaced_custom_object.return_value = {
        "status": {"readyInstances": 1, "phase": "Cluster in healthy state"},
        "spec": {"instances": 1},
    }
    return k8s


@pytest.fixture
def harbor_mock():
    harbor = MagicMock()
    harbor.create_project = AsyncMock()
    harbor.delete_project = AsyncMock()
    harbor.create_robot_account = AsyncMock(return_value={"name": "robot", "secret": "pass"})
    harbor.build_imagepull_secret = MagicMock(return_value={
        "metadata": {"name": "harbor-registry-secret"},
        "type": "kubernetes.io/dockerconfigjson",
        "data": {".dockerconfigjson": "e30="},
    })
    return harbor


@pytest_asyncio.fixture
async def client(db, k8s_mock):
    """Async HTTPX test client with DB, K8s, and auth overrides."""

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: k8s_mock
    app.dependency_overrides[verify_token] = lambda: {"sub": "test-user", "email": "test@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: mock external services (Keycloak, GitOps, Harbor)
# ---------------------------------------------------------------------------


def _patch_externals():
    """Patch all external service calls that would fail in test env."""
    return [
        patch("app.routers.tenants.keycloak_service.create_realm", new_callable=AsyncMock),
        patch("app.routers.tenants.keycloak_service.delete_realm", new_callable=AsyncMock),
        patch("app.routers.tenants.gitops_scaffold.scaffold_tenant", new_callable=AsyncMock),
        patch("app.routers.tenants.gitops_scaffold.delete_tenant", new_callable=AsyncMock),
        patch("app.routers.applications.gitops_scaffold.scaffold_app", new_callable=AsyncMock),
        patch("app.routers.applications.gitops_scaffold.delete_app", new_callable=AsyncMock),
        patch("app.services.tenant_service.HarborService", return_value=MagicMock(
            create_project=AsyncMock(),
            delete_project=AsyncMock(),
            create_robot_account=AsyncMock(return_value={"name": "robot", "secret": "pass"}),
            build_imagepull_secret=MagicMock(return_value={
                "metadata": {"name": "harbor-registry-secret"},
                "type": "kubernetes.io/dockerconfigjson",
                "data": {".dockerconfigjson": "e30="},
            }),
        )),
    ]


# ---------------------------------------------------------------------------
# Tenant creation payloads
# ---------------------------------------------------------------------------

ROTTERDAM = {
    "slug": "rotterdam",
    "name": "Gemeente Rotterdam",
    "tier": "starter",
    "cpu_limit": "8",
    "memory_limit": "16Gi",
    "storage_limit": "100Gi",
}

AMSTERDAM = {
    "slug": "amsterdam",
    "name": "Gemeente Amsterdam",
    "tier": "pro",
    "cpu_limit": "16",
    "memory_limit": "32Gi",
    "storage_limit": "200Gi",
}

UTRECHT = {
    "slug": "utrecht",
    "name": "Gemeente Utrecht",
    "tier": "starter",
    "cpu_limit": "8",
    "memory_limit": "16Gi",
    "storage_limit": "100Gi",
}


# ===========================================================================
# TEST CLASS: Multi-Tenant Full Lifecycle
# ===========================================================================


class TestMultiTenantLifecycle:
    """Full E2E lifecycle for 3 tenants with different managed services."""

    # -----------------------------------------------------------------------
    # 1. Tenant Creation
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_rotterdam_tenant(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            r = await client.post("/api/v1/tenants", json=ROTTERDAM)
        assert r.status_code == 201
        data = r.json()
        assert data["slug"] == "rotterdam"
        assert data["namespace"] == "tenant-rotterdam"
        assert data["tier"] == "starter"

    @pytest.mark.asyncio
    async def test_create_amsterdam_tenant(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            r = await client.post("/api/v1/tenants", json=AMSTERDAM)
        assert r.status_code == 201
        data = r.json()
        assert data["slug"] == "amsterdam"
        assert data["namespace"] == "tenant-amsterdam"
        assert data["tier"] == "pro"

    @pytest.mark.asyncio
    async def test_create_utrecht_tenant(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            r = await client.post("/api/v1/tenants", json=UTRECHT)
        assert r.status_code == 201
        data = r.json()
        assert data["slug"] == "utrecht"
        assert data["namespace"] == "tenant-utrecht"

    @pytest.mark.asyncio
    async def test_duplicate_tenant_slug_rejected(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            r = await client.post("/api/v1/tenants", json=ROTTERDAM)
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_list_tenants_returns_all(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            await client.post("/api/v1/tenants", json=UTRECHT)
            r = await client.get("/api/v1/tenants")
        assert r.status_code == 200
        slugs = {t["slug"] for t in r.json()}
        assert slugs == {"rotterdam", "amsterdam", "utrecht"}

    # -----------------------------------------------------------------------
    # 2. Application Creation per Tenant
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_app_for_rotterdam(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            r = await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "Rotterdam API",
                "slug": "rotterdam-api",
                "repo_url": "https://github.com/NimbusProTch/rotterdam-api",
                "branch": "main",
                "port": 8080,
            })
        assert r.status_code == 201
        data = r.json()
        assert data["slug"] == "rotterdam-api"
        assert data["port"] == 8080

    @pytest.mark.asyncio
    async def test_create_app_for_amsterdam(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            r = await client.post("/api/v1/tenants/amsterdam/apps", json={
                "name": "Amsterdam Portal",
                "slug": "amsterdam-portal",
                "repo_url": "https://github.com/NimbusProTch/amsterdam-portal",
                "branch": "main",
                "port": 3000,
            })
        assert r.status_code == 201
        assert r.json()["slug"] == "amsterdam-portal"

    @pytest.mark.asyncio
    async def test_create_app_for_utrecht(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=UTRECHT)
            r = await client.post("/api/v1/tenants/utrecht/apps", json={
                "name": "Utrecht Worker",
                "slug": "utrecht-worker",
                "repo_url": "https://github.com/NimbusProTch/utrecht-worker",
                "branch": "main",
                "port": 8080,
                "app_type": "worker",
            })
        assert r.status_code == 201
        assert r.json()["app_type"] == "worker"

    @pytest.mark.asyncio
    async def test_app_slug_unique_per_tenant(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            app_payload = {
                "name": "My App",
                "slug": "my-app",
                "repo_url": "https://github.com/org/repo",
                "branch": "main",
            }
            await client.post("/api/v1/tenants/rotterdam/apps", json=app_payload)
            r = await client.post("/api/v1/tenants/rotterdam/apps", json=app_payload)
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_same_app_slug_different_tenants_allowed(self, client, k8s_mock):
        """Same app slug is allowed in different tenants (namespace isolation)."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            app_payload = {
                "name": "Shared Name",
                "slug": "shared-app",
                "repo_url": "https://github.com/org/repo",
                "branch": "main",
            }
            r1 = await client.post("/api/v1/tenants/rotterdam/apps", json=app_payload)
            r2 = await client.post("/api/v1/tenants/amsterdam/apps", json=app_payload)
        assert r1.status_code == 201
        assert r2.status_code == 201

    @pytest.mark.asyncio
    async def test_list_apps_scoped_to_tenant(self, client, k8s_mock):
        """Apps are scoped to their tenant — listing returns only that tenant's apps."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "App A", "slug": "app-aaa", "repo_url": "https://github.com/a/b", "branch": "main",
            })
            await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "App B", "slug": "app-bbb", "repo_url": "https://github.com/a/c", "branch": "main",
            })
            await client.post("/api/v1/tenants/amsterdam/apps", json={
                "name": "App C", "slug": "app-ccc", "repo_url": "https://github.com/a/d", "branch": "main",
            })
            r_rot = await client.get("/api/v1/tenants/rotterdam/apps")
            r_ams = await client.get("/api/v1/tenants/amsterdam/apps")

        assert len(r_rot.json()) == 2
        assert len(r_ams.json()) == 1
        assert {a["slug"] for a in r_rot.json()} == {"app-aaa", "app-bbb"}
        assert r_ams.json()[0]["slug"] == "app-ccc"


# ===========================================================================
# TEST CLASS: Managed Service Provisioning (All 5 Types)
# ===========================================================================


class TestManagedServiceProvisioning:
    """Test provisioning all 5 service types across tenants."""

    # -----------------------------------------------------------------------
    # PostgreSQL (Rotterdam — Everest path)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_provision_postgres_via_everest(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = True
            mock_ev.create_database = AsyncMock()
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            r = await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "app-pg",
                "service_type": "postgres",
                "tier": "dev",
                "db_name": "rotterdam_db",
                "db_user": "rotterdam_user",
            })
        assert r.status_code == 201
        data = r.json()
        assert data["service_type"] == "postgres"
        assert data["status"] == "provisioning"
        assert data["secret_name"] == f"everest-secrets-rotterdam-app-pg"
        mock_ev.create_database.assert_called_once_with(
            name="rotterdam-app-pg",
            engine_type="postgres",
            tier="dev",
        )

    @pytest.mark.asyncio
    async def test_provision_postgres_via_crd_fallback(self, client, k8s_mock):
        """If Everest is not configured, fall back to CNPG CRD."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            r = await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "app-pg",
                "service_type": "postgres",
                "tier": "dev",
                "db_name": "mydb",
                "db_user": "myuser",
            })
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "provisioning"
        # CRD path uses CNPG secret naming
        assert data["secret_name"] == "app-pg-app"
        # Custom db_name should be reflected in connection hint
        assert "mydb" in data["connection_hint"]

    # -----------------------------------------------------------------------
    # Redis (Rotterdam — CRD path, always)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_provision_redis_crd(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = True  # Even with Everest, Redis uses CRD
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            r = await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "app-redis",
                "service_type": "redis",
                "tier": "dev",
            })
        assert r.status_code == 201
        data = r.json()
        assert data["service_type"] == "redis"
        assert data["status"] == "provisioning"
        assert "redis://" in data["connection_hint"]
        # Verify CRD was created, not Everest
        mock_ev.create_database.assert_not_called()
        k8s_mock.custom_objects.create_namespaced_custom_object.assert_called()

    @pytest.mark.asyncio
    async def test_redis_dev_tier_is_ephemeral(self):
        """Dev tier Redis has no persistent storage."""
        body = _redis_body("test-redis", "tenant-test", ServiceTier.DEV)
        assert "storage" not in body["spec"]

    @pytest.mark.asyncio
    async def test_redis_prod_tier_has_storage(self):
        """Prod tier Redis has persistent storage with Longhorn."""
        body = _redis_body("test-redis", "tenant-test", ServiceTier.PROD)
        assert "storage" in body["spec"]
        assert body["spec"]["storage"]["keepAfterDelete"] is True

    # -----------------------------------------------------------------------
    # MongoDB (Amsterdam — Everest path)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_provision_mongodb_via_everest(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = True
            mock_ev.create_database = AsyncMock()
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            r = await client.post("/api/v1/tenants/amsterdam/services", json={
                "name": "app-mongo",
                "service_type": "mongodb",
                "tier": "dev",
            })
        assert r.status_code == 201
        data = r.json()
        assert data["service_type"] == "mongodb"
        assert data["status"] == "provisioning"
        assert data["secret_name"] == "everest-secrets-amsterdam-app-mongo"
        mock_ev.create_database.assert_called_once_with(
            name="amsterdam-app-mongo",
            engine_type="mongodb",
            tier="dev",
        )

    @pytest.mark.asyncio
    async def test_provision_mongodb_via_crd_fallback(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            r = await client.post("/api/v1/tenants/amsterdam/services", json={
                "name": "app-mongo",
                "service_type": "mongodb",
                "tier": "dev",
            })
        assert r.status_code == 201
        data = r.json()
        assert data["secret_name"] == "app-mongo-psmdb-secrets"

    # -----------------------------------------------------------------------
    # MySQL (Utrecht — Everest path)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_provision_mysql_via_everest(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = True
            mock_ev.create_database = AsyncMock()
            await client.post("/api/v1/tenants", json=UTRECHT)
            r = await client.post("/api/v1/tenants/utrecht/services", json={
                "name": "app-mysql",
                "service_type": "mysql",
                "tier": "dev",
            })
        assert r.status_code == 201
        data = r.json()
        assert data["service_type"] == "mysql"
        assert data["status"] == "provisioning"
        mock_ev.create_database.assert_called_once_with(
            name="utrecht-app-mysql",
            engine_type="mysql",
            tier="dev",
        )

    @pytest.mark.asyncio
    async def test_provision_mysql_via_crd_fallback(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=UTRECHT)
            r = await client.post("/api/v1/tenants/utrecht/services", json={
                "name": "app-mysql",
                "service_type": "mysql",
                "tier": "dev",
            })
        assert r.status_code == 201
        data = r.json()
        assert data["secret_name"] == "app-mysql-pxc-secrets"

    # -----------------------------------------------------------------------
    # RabbitMQ (Utrecht — CRD path, always)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_provision_rabbitmq_crd(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = True
            await client.post("/api/v1/tenants", json=UTRECHT)
            r = await client.post("/api/v1/tenants/utrecht/services", json={
                "name": "app-rabbit",
                "service_type": "rabbitmq",
                "tier": "dev",
            })
        assert r.status_code == 201
        data = r.json()
        assert data["service_type"] == "rabbitmq"
        assert data["status"] == "provisioning"
        assert "amqp://" in data["connection_hint"]
        mock_ev.create_database.assert_not_called()

    # -----------------------------------------------------------------------
    # Service uniqueness within tenant
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_duplicate_service_name_rejected(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            svc = {"name": "my-redis", "service_type": "redis", "tier": "dev"}
            await client.post("/api/v1/tenants/rotterdam/services", json=svc)
            r = await client.post("/api/v1/tenants/rotterdam/services", json=svc)
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_same_service_name_different_tenants_allowed(self, client, k8s_mock):
        """Same service name is allowed in different tenants."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            svc = {"name": "shared-redis", "service_type": "redis", "tier": "dev"}
            r1 = await client.post("/api/v1/tenants/rotterdam/services", json=svc)
            r2 = await client.post("/api/v1/tenants/amsterdam/services", json=svc)
        assert r1.status_code == 201
        assert r2.status_code == 201

    # -----------------------------------------------------------------------
    # Services scoped to tenant
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_services_scoped_to_tenant(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "pg-one", "service_type": "redis", "tier": "dev",
            })
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "pg-two", "service_type": "redis", "tier": "dev",
            })
            await client.post("/api/v1/tenants/amsterdam/services", json={
                "name": "mg-one", "service_type": "redis", "tier": "dev",
            })
            r_rot = await client.get("/api/v1/tenants/rotterdam/services")
            r_ams = await client.get("/api/v1/tenants/amsterdam/services")

        assert len(r_rot.json()) == 2
        assert len(r_ams.json()) == 1


# ===========================================================================
# TEST CLASS: CRD Body Builders (all 5 types)
# ===========================================================================


class TestCRDBodyBuilders:
    """Verify CRD manifests are correctly constructed for all service types."""

    def test_cnpg_cluster_dev(self):
        body = _cnpg_cluster_body("my-pg", "tenant-test", ServiceTier.DEV)
        assert body["kind"] == "Cluster"
        assert body["spec"]["instances"] == 1
        assert body["spec"]["storage"]["size"] == "5Gi"
        assert body["spec"]["bootstrap"]["initdb"]["database"] == "my_pg"

    def test_cnpg_cluster_prod(self):
        body = _cnpg_cluster_body("my-pg", "tenant-test", ServiceTier.PROD)
        assert body["spec"]["instances"] == 3
        assert body["spec"]["storage"]["size"] == "20Gi"

    def test_cnpg_custom_db_name(self):
        body = _cnpg_cluster_body("my-pg", "tenant-test", ServiceTier.DEV, db_name="custom_db", db_user="custom_user")
        assert body["spec"]["bootstrap"]["initdb"]["database"] == "custom_db"
        assert body["spec"]["bootstrap"]["initdb"]["owner"] == "custom_user"

    def test_redis_dev_no_storage(self):
        body = _redis_body("app-redis", "tenant-test", ServiceTier.DEV)
        assert "storage" not in body["spec"]
        assert body["spec"]["tolerations"] == [{"operator": "Exists"}]

    def test_redis_prod_with_storage(self):
        body = _redis_body("app-redis", "tenant-test", ServiceTier.PROD)
        assert body["spec"]["storage"]["keepAfterDelete"] is True
        storage_spec = body["spec"]["storage"]["volumeClaimTemplate"]["spec"]
        assert storage_spec["storageClassName"] == "longhorn"
        assert storage_spec["resources"]["requests"]["storage"] == "5Gi"

    def test_rabbitmq_dev(self):
        body = _rabbitmq_body("app-rabbit", "tenant-test", ServiceTier.DEV)
        assert body["kind"] == "RabbitmqCluster"
        assert body["spec"]["replicas"] == 1
        assert body["spec"]["persistence"]["storage"] == "5Gi"

    def test_rabbitmq_prod(self):
        body = _rabbitmq_body("app-rabbit", "tenant-test", ServiceTier.PROD)
        assert body["spec"]["replicas"] == 3
        assert body["spec"]["persistence"]["storage"] == "10Gi"

    def test_mysql_dev(self):
        body = _mysql_body("app-mysql", "tenant-test", ServiceTier.DEV)
        assert body["kind"] == "PerconaXtraDBCluster"
        assert body["spec"]["pxc"]["size"] == 1
        assert body["spec"]["allowUnsafeConfigurations"] is True
        assert body["spec"]["haproxy"]["size"] == 1

    def test_mysql_prod(self):
        body = _mysql_body("app-mysql", "tenant-test", ServiceTier.PROD)
        assert body["spec"]["pxc"]["size"] == 3
        assert body["spec"]["allowUnsafeConfigurations"] is False
        assert body["spec"]["haproxy"]["size"] == 2

    def test_mongodb_dev(self):
        body = _mongodb_body("app-mongo", "tenant-test", ServiceTier.DEV)
        assert body["kind"] == "PerconaServerMongoDB"
        assert body["spec"]["replsets"][0]["size"] == 1
        assert body["spec"]["allowUnsafeConfigurations"] is True
        assert body["spec"]["sharding"]["enabled"] is False

    def test_mongodb_prod(self):
        body = _mongodb_body("app-mongo", "tenant-test", ServiceTier.PROD)
        assert body["spec"]["replsets"][0]["size"] == 3
        assert body["spec"]["allowUnsafeConfigurations"] is False


# ===========================================================================
# TEST CLASS: Service Connect/Disconnect
# ===========================================================================


class TestServiceConnectDisconnect:
    """Test connecting/disconnecting managed services to apps."""

    async def _setup_tenant_app_service(self, client, k8s_mock, tenant_slug, svc_name, svc_type):
        """Helper: create tenant + app + service, mark service READY."""
        tenant_payload = {
            "slug": tenant_slug,
            "name": f"Tenant {tenant_slug}",
            "tier": "starter",
            "cpu_limit": "8",
            "memory_limit": "16Gi",
            "storage_limit": "100Gi",
        }
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=tenant_payload)
            await client.post(f"/api/v1/tenants/{tenant_slug}/apps", json={
                "name": "Test App",
                "slug": "test-app",
                "repo_url": "https://github.com/org/repo",
                "branch": "main",
                "port": 8080,
            })
            await client.post(f"/api/v1/tenants/{tenant_slug}/services", json={
                "name": svc_name,
                "service_type": svc_type,
                "tier": "dev",
            })

    @pytest.mark.asyncio
    async def test_connect_postgres_to_app(self, client, db, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "Test App", "slug": "test-app",
                "repo_url": "https://github.com/org/repo", "branch": "main",
            })
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "main-pg", "service_type": "postgres", "tier": "dev",
            })

            # Manually mark service as READY for connect-service
            result = await db.execute(select(ManagedService).where(ManagedService.name == "main-pg"))
            svc = result.scalar_one()
            svc.status = ServiceStatus.READY
            svc.secret_name = "main-pg-app"
            svc.service_namespace = "tenant-rotterdam"
            svc.connection_hint = "postgresql://main_pg_user@main-pg-rw.tenant-rotterdam.svc:5432/main_pg"
            await db.commit()

            r = await client.post("/api/v1/tenants/rotterdam/apps/test-app/connect-service", json={
                "service_name": "main-pg",
            })

        assert r.status_code == 200
        data = r.json()
        assert data["env_from_secrets"] is not None
        assert len(data["env_from_secrets"]) == 1
        assert data["env_from_secrets"][0]["service_name"] == "main-pg"
        assert data["env_vars"]["DATABASE_URL"] == svc.connection_hint

    @pytest.mark.asyncio
    async def test_connect_redis_to_app(self, client, db, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "Test App", "slug": "test-app",
                "repo_url": "https://github.com/org/repo", "branch": "main",
            })
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "app-cache", "service_type": "redis", "tier": "dev",
            })

            result = await db.execute(select(ManagedService).where(ManagedService.name == "app-cache"))
            svc = result.scalar_one()
            svc.status = ServiceStatus.READY
            svc.secret_name = "app-cache-redis"
            svc.service_namespace = "tenant-rotterdam"
            svc.connection_hint = "redis://app-cache.tenant-rotterdam.svc:6379"
            await db.commit()

            r = await client.post("/api/v1/tenants/rotterdam/apps/test-app/connect-service", json={
                "service_name": "app-cache",
            })

        assert r.status_code == 200
        # Redis has no DATABASE_URL key, but env_from_secrets should be set
        data = r.json()
        assert len(data["env_from_secrets"]) == 1

    @pytest.mark.asyncio
    async def test_connect_rabbitmq_to_app(self, client, db, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=UTRECHT)
            await client.post("/api/v1/tenants/utrecht/apps", json={
                "name": "Worker", "slug": "worker-app",
                "repo_url": "https://github.com/org/repo", "branch": "main",
            })
            await client.post("/api/v1/tenants/utrecht/services", json={
                "name": "app-mq", "service_type": "rabbitmq", "tier": "dev",
            })

            result = await db.execute(select(ManagedService).where(ManagedService.name == "app-mq"))
            svc = result.scalar_one()
            svc.status = ServiceStatus.READY
            svc.secret_name = "app-mq-default-user"
            svc.service_namespace = "tenant-utrecht"
            svc.connection_hint = "amqp://app-mq-default-user@app-mq.tenant-utrecht.svc:5672"
            await db.commit()

            r = await client.post("/api/v1/tenants/utrecht/apps/worker-app/connect-service", json={
                "service_name": "app-mq",
            })

        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_connect_service_not_ready_rejected(self, client, db, k8s_mock):
        """Cannot connect a service that is still provisioning."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "App", "slug": "test-app",
                "repo_url": "https://github.com/org/repo", "branch": "main",
            })
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "new-pg", "service_type": "redis", "tier": "dev",
            })
            # Service is still PROVISIONING, no manual status change
            r = await client.post("/api/v1/tenants/rotterdam/apps/test-app/connect-service", json={
                "service_name": "new-pg",
            })
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_disconnect_service_from_app(self, client, db, k8s_mock):
        """Disconnect removes env_from_secrets entry and cleans up env_vars."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "App", "slug": "test-app",
                "repo_url": "https://github.com/org/repo", "branch": "main",
            })
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "my-pg", "service_type": "postgres", "tier": "dev",
            })

            # Mark ready and connect
            result = await db.execute(select(ManagedService).where(ManagedService.name == "my-pg"))
            svc = result.scalar_one()
            svc.status = ServiceStatus.READY
            svc.secret_name = "my-pg-app"
            svc.service_namespace = "tenant-rotterdam"
            svc.connection_hint = "postgresql://user@my-pg-rw.tenant-rotterdam.svc:5432/my_pg"
            await db.commit()

            await client.post("/api/v1/tenants/rotterdam/apps/test-app/connect-service", json={
                "service_name": "my-pg",
            })

            # Now disconnect
            r = await client.delete("/api/v1/tenants/rotterdam/apps/test-app/connect-service/my-pg")

        assert r.status_code == 204

        # Verify env_from_secrets is empty
        r2 = await client.get("/api/v1/tenants/rotterdam/apps/test-app")
        data = r2.json()
        assert data["env_from_secrets"] is None or len(data["env_from_secrets"]) == 0


# ===========================================================================
# TEST CLASS: Service Status Sync (Everest + CRD paths)
# ===========================================================================


class TestServiceStatusSync:
    """Test status synchronization for all service types."""

    @pytest.mark.asyncio
    async def test_everest_pg_status_sync_ready(self):
        k8s = MagicMock()
        k8s.is_available.return_value = True
        mock_ev = MagicMock()
        mock_ev.is_configured.return_value = True
        mock_ev.get_database_status = AsyncMock(return_value="ready")

        provisioner = ManagedServiceProvisioner(k8s, everest=mock_ev)
        svc = ManagedService(
            name="test-pg", service_type=ServiceType.POSTGRES, tier=ServiceTier.DEV,
            status=ServiceStatus.PROVISIONING, everest_name="tenant-test-pg",
        )
        await provisioner.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_everest_mysql_status_sync_failed(self):
        k8s = MagicMock()
        k8s.is_available.return_value = True
        mock_ev = MagicMock()
        mock_ev.is_configured.return_value = True
        mock_ev.get_database_status = AsyncMock(return_value="error")

        provisioner = ManagedServiceProvisioner(k8s, everest=mock_ev)
        svc = ManagedService(
            name="test-mysql", service_type=ServiceType.MYSQL, tier=ServiceTier.DEV,
            status=ServiceStatus.PROVISIONING, everest_name="tenant-test-mysql",
        )
        await provisioner.sync_status(svc)
        assert svc.status == ServiceStatus.FAILED

    @pytest.mark.asyncio
    async def test_crd_redis_status_sync_ready(self):
        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.custom_objects = MagicMock()
        k8s.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"readyReplicas": 1},
        }
        mock_ev = MagicMock()
        mock_ev.is_configured.return_value = False

        provisioner = ManagedServiceProvisioner(k8s, everest=mock_ev)
        svc = ManagedService(
            name="app-redis", service_type=ServiceType.REDIS, tier=ServiceTier.DEV,
            status=ServiceStatus.PROVISIONING, service_namespace="tenant-test",
        )
        await provisioner.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_crd_rabbitmq_status_sync_ready(self):
        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.custom_objects = MagicMock()
        k8s.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {
                "conditions": [
                    {"type": "AllReplicasReady", "status": "True"},
                ]
            },
        }
        mock_ev = MagicMock()
        mock_ev.is_configured.return_value = False

        provisioner = ManagedServiceProvisioner(k8s, everest=mock_ev)
        svc = ManagedService(
            name="app-rabbit", service_type=ServiceType.RABBITMQ, tier=ServiceTier.DEV,
            status=ServiceStatus.PROVISIONING, service_namespace="tenant-test",
        )
        await provisioner.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_crd_postgres_status_sync_healthy(self):
        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.custom_objects = MagicMock()
        k8s.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"phase": "Cluster in healthy state", "readyInstances": 1},
            "spec": {"instances": 1},
        }
        mock_ev = MagicMock()
        mock_ev.is_configured.return_value = False

        provisioner = ManagedServiceProvisioner(k8s, everest=mock_ev)
        svc = ManagedService(
            name="app-pg", service_type=ServiceType.POSTGRES, tier=ServiceTier.DEV,
            status=ServiceStatus.PROVISIONING, service_namespace="tenant-test",
        )
        await provisioner.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_crd_mysql_status_sync_ready(self):
        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.custom_objects = MagicMock()
        k8s.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"state": "ready"},
        }
        mock_ev = MagicMock()
        mock_ev.is_configured.return_value = False

        provisioner = ManagedServiceProvisioner(k8s, everest=mock_ev)
        svc = ManagedService(
            name="app-mysql", service_type=ServiceType.MYSQL, tier=ServiceTier.DEV,
            status=ServiceStatus.PROVISIONING, service_namespace="tenant-test",
        )
        await provisioner.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_crd_mongodb_status_sync_ready(self):
        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.custom_objects = MagicMock()
        k8s.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"state": "ready"},
        }
        mock_ev = MagicMock()
        mock_ev.is_configured.return_value = False

        provisioner = ManagedServiceProvisioner(k8s, everest=mock_ev)
        svc = ManagedService(
            name="app-mongo", service_type=ServiceType.MONGODB, tier=ServiceTier.DEV,
            status=ServiceStatus.PROVISIONING, service_namespace="tenant-test",
        )
        await provisioner.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_crd_404_sets_failed(self):
        """If CRD not found (404), status → FAILED."""
        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.custom_objects = MagicMock()
        k8s.custom_objects.get_namespaced_custom_object.side_effect = ApiException(status=404)
        mock_ev = MagicMock()
        mock_ev.is_configured.return_value = False

        provisioner = ManagedServiceProvisioner(k8s, everest=mock_ev)
        svc = ManagedService(
            name="gone-svc", service_type=ServiceType.REDIS, tier=ServiceTier.DEV,
            status=ServiceStatus.PROVISIONING, service_namespace="tenant-test",
        )
        await provisioner.sync_status(svc)
        assert svc.status == ServiceStatus.FAILED


# ===========================================================================
# TEST CLASS: Service Credentials
# ===========================================================================


class TestServiceCredentials:
    """Test the /credentials endpoint."""

    @pytest.mark.asyncio
    async def test_credentials_returned_when_ready(self, client, db, k8s_mock):
        import base64

        # Setup secret data on mock
        k8s_mock.core_v1.read_namespaced_secret.return_value = MagicMock(
            data={
                "username": base64.b64encode(b"pguser").decode(),
                "password": base64.b64encode(b"pgpass123").decode(),
                "host": base64.b64encode(b"pg-rw.tenant-rotterdam.svc").decode(),
            }
        )

        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "cred-pg", "service_type": "postgres", "tier": "dev",
            })

            # Mark READY
            result = await db.execute(select(ManagedService).where(ManagedService.name == "cred-pg"))
            svc = result.scalar_one()
            svc.status = ServiceStatus.READY
            svc.secret_name = "cred-pg-app"
            svc.service_namespace = "tenant-rotterdam"
            svc.connection_hint = "postgresql://user@host:5432/db"
            await db.commit()

            r = await client.get("/api/v1/tenants/rotterdam/services/cred-pg/credentials")

        assert r.status_code == 200
        data = r.json()
        assert data["credentials"]["username"] == "pguser"
        assert data["credentials"]["password"] == "pgpass123"
        assert data["credentials"]["host"] == "pg-rw.tenant-rotterdam.svc"

    @pytest.mark.asyncio
    async def test_credentials_rejected_when_not_ready(self, client, db, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "not-ready-pg", "service_type": "redis", "tier": "dev",
            })
            # Still PROVISIONING
            r = await client.get("/api/v1/tenants/rotterdam/services/not-ready-pg/credentials")
        assert r.status_code == 409


# ===========================================================================
# TEST CLASS: Tenant Deletion + Full Cleanup
# ===========================================================================


class TestTenantDeletion:
    """Test that deleting a tenant cleans up everything."""

    @pytest.mark.asyncio
    async def test_delete_tenant_cascades_services_and_apps(self, client, db, k8s_mock):
        """Deleting a tenant removes all services, apps from DB."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            mock_ev.delete_database = AsyncMock()
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "App A", "slug": "app-aaa",
                "repo_url": "https://github.com/org/repo", "branch": "main",
            })
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "svc-redis", "service_type": "redis", "tier": "dev",
            })

            # Verify they exist
            r_apps = await client.get("/api/v1/tenants/rotterdam/apps")
            r_svcs = await client.get("/api/v1/tenants/rotterdam/services")
            assert len(r_apps.json()) == 1
            assert len(r_svcs.json()) == 1

            # Delete tenant
            r = await client.delete("/api/v1/tenants/rotterdam")
            assert r.status_code == 204

            # Verify tenant gone
            r_get = await client.get("/api/v1/tenants/rotterdam")
            assert r_get.status_code == 404

            # Verify cascade: apps and services gone from DB
            result_apps = await db.execute(select(Application))
            assert list(result_apps.scalars()) == []
            result_svcs = await db.execute(select(ManagedService))
            assert list(result_svcs.scalars()) == []

    @pytest.mark.asyncio
    async def test_delete_tenant_calls_k8s_cleanup(self, client, db, k8s_mock):
        """Deleting a tenant deletes namespace and ApplicationSet via K8s."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.delete("/api/v1/tenants/rotterdam")

        # Namespace deleted
        k8s_mock.core_v1.delete_namespace.assert_called_with("tenant-rotterdam")

        # ApplicationSet deleted
        k8s_mock.custom_objects.delete_namespaced_custom_object.assert_any_call(
            group="argoproj.io",
            version="v1alpha1",
            namespace="argocd",
            plural="applicationsets",
            name="appset-rotterdam",
        )

    @pytest.mark.asyncio
    async def test_delete_tenant_deprovisions_everest_dbs(self, client, db, k8s_mock):
        """Deleting a tenant with Everest DBs calls Everest delete API."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = True
            mock_ev.create_database = AsyncMock()
            mock_ev.delete_database = AsyncMock()

            await client.post("/api/v1/tenants", json=AMSTERDAM)
            await client.post("/api/v1/tenants/amsterdam/services", json={
                "name": "mongo-db", "service_type": "mongodb", "tier": "dev",
            })

            # Mark it with everest_name
            result = await db.execute(select(ManagedService).where(ManagedService.name == "mongo-db"))
            svc = result.scalar_one()
            assert svc.everest_name == "amsterdam-mongo-db"

            await client.delete("/api/v1/tenants/amsterdam")

        mock_ev.delete_database.assert_called_once_with("amsterdam-mongo-db")

    @pytest.mark.asyncio
    async def test_delete_tenant_deprovisions_crd_services(self, client, db, k8s_mock):
        """Deleting a tenant with CRD services calls K8s delete."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False

            await client.post("/api/v1/tenants", json=UTRECHT)
            await client.post("/api/v1/tenants/utrecht/services", json={
                "name": "my-redis", "service_type": "redis", "tier": "dev",
            })
            await client.post("/api/v1/tenants/utrecht/services", json={
                "name": "my-rabbit", "service_type": "rabbitmq", "tier": "dev",
            })

            await client.delete("/api/v1/tenants/utrecht")

        # Both CRDs should be deleted
        delete_calls = k8s_mock.custom_objects.delete_namespaced_custom_object.call_args_list
        deleted_names = [c.kwargs.get("name") for c in delete_calls if c.kwargs.get("name")]
        assert "my-redis" in deleted_names
        assert "my-rabbit" in deleted_names

    @pytest.mark.asyncio
    async def test_delete_multiple_tenants_independently(self, client, db, k8s_mock):
        """Deleting one tenant does not affect others."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False

            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "rot-redis", "service_type": "redis", "tier": "dev",
            })
            await client.post("/api/v1/tenants/amsterdam/services", json={
                "name": "ams-redis", "service_type": "redis", "tier": "dev",
            })

            # Delete rotterdam
            r = await client.delete("/api/v1/tenants/rotterdam")
            assert r.status_code == 204

            # Amsterdam still exists with its services
            r_ams = await client.get("/api/v1/tenants/amsterdam")
            assert r_ams.status_code == 200
            r_svcs = await client.get("/api/v1/tenants/amsterdam/services")
            assert len(r_svcs.json()) == 1
            assert r_svcs.json()[0]["name"] == "ams-redis"


# ===========================================================================
# TEST CLASS: Service Delete (individual)
# ===========================================================================


class TestServiceDelete:
    """Test deleting individual services."""

    @pytest.mark.asyncio
    async def test_delete_redis_service(self, client, db, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "del-redis", "service_type": "redis", "tier": "dev",
            })

            r = await client.delete("/api/v1/tenants/rotterdam/services/del-redis")
        assert r.status_code == 204

        # Verify gone from DB
        result = await db.execute(select(ManagedService).where(ManagedService.name == "del-redis"))
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_everest_service(self, client, db, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = True
            mock_ev.create_database = AsyncMock()
            mock_ev.delete_database = AsyncMock()
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            await client.post("/api/v1/tenants/amsterdam/services", json={
                "name": "del-pg", "service_type": "postgres", "tier": "dev",
            })

            r = await client.delete("/api/v1/tenants/amsterdam/services/del-pg")
        assert r.status_code == 204
        mock_ev.delete_database.assert_called_once_with("amsterdam-del-pg")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_service_returns_404(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            r = await client.delete("/api/v1/tenants/rotterdam/services/nonexistent")
        assert r.status_code == 404


# ===========================================================================
# TEST CLASS: ApplicationSet Per Tenant
# ===========================================================================


class TestApplicationSetPerTenant:
    """Verify each tenant gets its own ArgoCD ApplicationSet."""

    @pytest.mark.asyncio
    async def test_appset_created_on_tenant_provision(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)

        # Find the ApplicationSet creation call
        calls = k8s_mock.custom_objects.create_namespaced_custom_object.call_args_list
        appset_calls = [c for c in calls if c.kwargs.get("plural") == "applicationsets"]
        assert len(appset_calls) == 1
        body = appset_calls[0].kwargs["body"]
        assert body["metadata"]["name"] == "appset-rotterdam"
        assert body["metadata"]["labels"]["haven.io/tenant"] == "rotterdam"

    @pytest.mark.asyncio
    async def test_three_tenants_three_appsets(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            await client.post("/api/v1/tenants", json=UTRECHT)

        calls = k8s_mock.custom_objects.create_namespaced_custom_object.call_args_list
        appset_calls = [c for c in calls if c.kwargs.get("plural") == "applicationsets"]
        appset_names = {c.kwargs["body"]["metadata"]["name"] for c in appset_calls}
        assert appset_names == {"appset-rotterdam", "appset-amsterdam", "appset-utrecht"}

    @pytest.mark.asyncio
    async def test_appset_deleted_on_tenant_delete(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.delete("/api/v1/tenants/rotterdam")

        delete_calls = k8s_mock.custom_objects.delete_namespaced_custom_object.call_args_list
        appset_deletes = [c for c in delete_calls if c.kwargs.get("name") == "appset-rotterdam"]
        assert len(appset_deletes) == 1


# ===========================================================================
# TEST CLASS: Connection Hint Correctness
# ===========================================================================


class TestConnectionHints:
    """Verify connection hints are correct for all service types."""

    def test_postgres_connection_hint(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.POSTGRES]("my-pg", "tenant-test")
        assert hint.startswith("postgresql://")
        assert "my-pg-rw.tenant-test.svc:5432" in hint

    def test_mysql_connection_hint(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.MYSQL]("my-mysql", "tenant-test")
        assert hint.startswith("mysql://")
        assert "my-mysql-haproxy.tenant-test.svc:3306" in hint

    def test_mongodb_connection_hint(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.MONGODB]("my-mongo", "tenant-test")
        assert hint.startswith("mongodb://")
        assert "my-mongo-mongos.tenant-test.svc:27017" in hint

    def test_redis_connection_hint(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.REDIS]("my-redis", "tenant-test")
        assert hint == "redis://my-redis.tenant-test.svc:6379"

    def test_rabbitmq_connection_hint(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.RABBITMQ]("my-rabbit", "tenant-test")
        assert hint.startswith("amqp://")
        assert "my-rabbit.tenant-test.svc:5672" in hint


# ===========================================================================
# TEST CLASS: Secret Name Correctness
# ===========================================================================


class TestSecretNames:
    """Verify secret names follow conventions for all service types."""

    def test_postgres_secret_name(self):
        assert _SECRET_NAME_MAP[ServiceType.POSTGRES]("my-pg") == "my-pg-app"

    def test_mysql_secret_name(self):
        assert _SECRET_NAME_MAP[ServiceType.MYSQL]("my-mysql") == "my-mysql-pxc-secrets"

    def test_mongodb_secret_name(self):
        assert _SECRET_NAME_MAP[ServiceType.MONGODB]("my-mongo") == "my-mongo-psmdb-secrets"

    def test_redis_secret_name(self):
        assert _SECRET_NAME_MAP[ServiceType.REDIS]("my-redis") == "my-redis-redis"

    def test_rabbitmq_secret_name(self):
        assert _SECRET_NAME_MAP[ServiceType.RABBITMQ]("my-rabbit") == "my-rabbit-default-user"

    def test_everest_secret_name(self):
        assert _EVEREST_SECRET_NAME("tenant-db") == "everest-secrets-tenant-db"


# ===========================================================================
# TEST CLASS: Everest Tenant Prefix Isolation
# ===========================================================================


class TestEverestTenantPrefix:
    """Verify Everest DB names are prefixed with tenant slug."""

    @pytest.mark.asyncio
    async def test_everest_name_prefixed_rotterdam(self, client, db, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = True
            mock_ev.create_database = AsyncMock()
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "main-db", "service_type": "postgres", "tier": "dev",
            })

        result = await db.execute(select(ManagedService).where(ManagedService.name == "main-db"))
        svc = result.scalar_one()
        assert svc.everest_name == "rotterdam-main-db"

    @pytest.mark.asyncio
    async def test_everest_name_prefixed_amsterdam(self, client, db, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = True
            mock_ev.create_database = AsyncMock()
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            await client.post("/api/v1/tenants/amsterdam/services", json={
                "name": "main-db", "service_type": "mongodb", "tier": "dev",
            })

        result = await db.execute(select(ManagedService).where(ManagedService.name == "main-db"))
        svc = result.scalar_one()
        assert svc.everest_name == "amsterdam-main-db"

    @pytest.mark.asyncio
    async def test_same_service_name_different_everest_names(self, client, db, k8s_mock):
        """Two tenants with same service name get different Everest DB names."""
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = True
            mock_ev.create_database = AsyncMock()
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants", json=AMSTERDAM)
            await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "shared-db", "service_type": "postgres", "tier": "dev",
            })
            await client.post("/api/v1/tenants/amsterdam/services", json={
                "name": "shared-db", "service_type": "postgres", "tier": "dev",
            })

        result = await db.execute(select(ManagedService))
        svcs = list(result.scalars())
        everest_names = {s.everest_name for s in svcs}
        assert everest_names == {"rotterdam-shared-db", "amsterdam-shared-db"}


# ===========================================================================
# TEST CLASS: Tenant Update
# ===========================================================================


class TestTenantUpdate:
    """Test tenant PATCH operations."""

    @pytest.mark.asyncio
    async def test_update_tenant_name(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            r = await client.patch("/api/v1/tenants/rotterdam", json={"name": "Rotterdam City"})
        assert r.status_code == 200
        assert r.json()["name"] == "Rotterdam City"
        assert r.json()["slug"] == "rotterdam"  # slug unchanged

    @pytest.mark.asyncio
    async def test_update_tenant_tier(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            r = await client.patch("/api/v1/tenants/rotterdam", json={"tier": "enterprise"})
        assert r.status_code == 200
        assert r.json()["tier"] == "enterprise"


# ===========================================================================
# TEST CLASS: Application Update
# ===========================================================================


class TestApplicationUpdate:
    """Test application PATCH operations."""

    @pytest.mark.asyncio
    async def test_update_app_env_vars(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "App", "slug": "test-app",
                "repo_url": "https://github.com/org/repo", "branch": "main",
            })
            r = await client.patch("/api/v1/tenants/rotterdam/apps/test-app", json={
                "env_vars": {"DATABASE_URL": "postgres://localhost/db", "REDIS_URL": "redis://localhost"},
            })
        assert r.status_code == 200
        assert r.json()["env_vars"]["DATABASE_URL"] == "postgres://localhost/db"
        assert r.json()["env_vars"]["REDIS_URL"] == "redis://localhost"

    @pytest.mark.asyncio
    async def test_update_app_replicas(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "App", "slug": "test-app",
                "repo_url": "https://github.com/org/repo", "branch": "main",
            })
            r = await client.patch("/api/v1/tenants/rotterdam/apps/test-app", json={"replicas": 3})
        assert r.status_code == 200
        assert r.json()["replicas"] == 3

    @pytest.mark.asyncio
    async def test_update_app_port(self, client, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6]:
            await client.post("/api/v1/tenants", json=ROTTERDAM)
            await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "App", "slug": "test-app",
                "repo_url": "https://github.com/org/repo", "branch": "main", "port": 8000,
            })
            r = await client.patch("/api/v1/tenants/rotterdam/apps/test-app", json={"port": 3000})
        assert r.status_code == 200
        assert r.json()["port"] == 3000


# ===========================================================================
# TEST CLASS: Full Integration Scenario
# ===========================================================================


class TestFullIntegrationScenario:
    """Run the complete 3-tenant scenario end-to-end in a single test.

    This mirrors the real-world flow:
    1. Create 3 tenants
    2. Create apps for each
    3. Provision services (PG+Redis for Rotterdam, MongoDB+Redis for Amsterdam, MySQL+RabbitMQ for Utrecht)
    4. Connect services to apps
    5. Verify isolation
    6. Delete all tenants and verify cleanup
    """

    @pytest.mark.asyncio
    async def test_three_tenant_full_lifecycle(self, client, db, k8s_mock):
        with _patch_externals()[0], _patch_externals()[1], _patch_externals()[2], \
             _patch_externals()[3], _patch_externals()[4], _patch_externals()[5], \
             _patch_externals()[6], \
             patch("app.services.managed_service.everest_client") as mock_ev:
            mock_ev.is_configured.return_value = False

            # === STEP 1: Create 3 tenants ===
            r1 = await client.post("/api/v1/tenants", json=ROTTERDAM)
            r2 = await client.post("/api/v1/tenants", json=AMSTERDAM)
            r3 = await client.post("/api/v1/tenants", json=UTRECHT)
            assert r1.status_code == 201
            assert r2.status_code == 201
            assert r3.status_code == 201

            # Verify 3 tenants in list
            tenants = await client.get("/api/v1/tenants")
            assert len(tenants.json()) == 3

            # === STEP 2: Create apps ===
            r_app1 = await client.post("/api/v1/tenants/rotterdam/apps", json={
                "name": "Rotterdam API", "slug": "rotterdam-api",
                "repo_url": "https://github.com/NimbusProTch/rotterdam-api",
                "branch": "main", "port": 8080,
            })
            r_app2 = await client.post("/api/v1/tenants/amsterdam/apps", json={
                "name": "Amsterdam Portal", "slug": "amsterdam-portal",
                "repo_url": "https://github.com/NimbusProTch/amsterdam-portal",
                "branch": "main", "port": 3000,
            })
            r_app3 = await client.post("/api/v1/tenants/utrecht/apps", json={
                "name": "Utrecht Worker", "slug": "utrecht-worker",
                "repo_url": "https://github.com/NimbusProTch/utrecht-worker",
                "branch": "main", "port": 8080, "app_type": "worker",
            })
            assert r_app1.status_code == 201
            assert r_app2.status_code == 201
            assert r_app3.status_code == 201

            # === STEP 3: Provision services ===
            # Rotterdam: PG + Redis
            r_pg = await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "main-pg", "service_type": "postgres", "tier": "dev",
            })
            r_redis1 = await client.post("/api/v1/tenants/rotterdam/services", json={
                "name": "cache", "service_type": "redis", "tier": "dev",
            })
            assert r_pg.status_code == 201
            assert r_redis1.status_code == 201

            # Amsterdam: MongoDB + Redis
            r_mongo = await client.post("/api/v1/tenants/amsterdam/services", json={
                "name": "main-mongo", "service_type": "mongodb", "tier": "dev",
            })
            r_redis2 = await client.post("/api/v1/tenants/amsterdam/services", json={
                "name": "cache", "service_type": "redis", "tier": "dev",
            })
            assert r_mongo.status_code == 201
            assert r_redis2.status_code == 201

            # Utrecht: MySQL + RabbitMQ
            r_mysql = await client.post("/api/v1/tenants/utrecht/services", json={
                "name": "main-mysql", "service_type": "mysql", "tier": "dev",
            })
            r_rabbit = await client.post("/api/v1/tenants/utrecht/services", json={
                "name": "task-queue", "service_type": "rabbitmq", "tier": "dev",
            })
            assert r_mysql.status_code == 201
            assert r_rabbit.status_code == 201

            # Verify service counts per tenant
            rot_svcs = await client.get("/api/v1/tenants/rotterdam/services")
            ams_svcs = await client.get("/api/v1/tenants/amsterdam/services")
            utr_svcs = await client.get("/api/v1/tenants/utrecht/services")
            assert len(rot_svcs.json()) == 2
            assert len(ams_svcs.json()) == 2
            assert len(utr_svcs.json()) == 2

            # === STEP 4: Connect services to apps ===
            # Mark all services READY for connection
            all_svcs = await db.execute(select(ManagedService))
            for svc in all_svcs.scalars():
                svc.status = ServiceStatus.READY
                svc.secret_name = svc.secret_name or f"{svc.name}-secret"
                svc.service_namespace = svc.service_namespace or f"tenant-{ROTTERDAM['slug']}"
                svc.connection_hint = svc.connection_hint or f"test://{svc.name}"
            await db.commit()

            # Connect Rotterdam PG to Rotterdam API
            r_conn1 = await client.post("/api/v1/tenants/rotterdam/apps/rotterdam-api/connect-service", json={
                "service_name": "main-pg",
            })
            assert r_conn1.status_code == 200

            # Connect Rotterdam Redis to Rotterdam API
            r_conn2 = await client.post("/api/v1/tenants/rotterdam/apps/rotterdam-api/connect-service", json={
                "service_name": "cache",
            })
            assert r_conn2.status_code == 200

            # Verify Rotterdam API has 2 connected services
            r_app_detail = await client.get("/api/v1/tenants/rotterdam/apps/rotterdam-api")
            assert len(r_app_detail.json()["env_from_secrets"]) == 2

            # Connect Amsterdam MongoDB to Amsterdam Portal
            r_conn3 = await client.post("/api/v1/tenants/amsterdam/apps/amsterdam-portal/connect-service", json={
                "service_name": "main-mongo",
            })
            assert r_conn3.status_code == 200

            # Connect Utrecht MySQL + RabbitMQ to Utrecht Worker
            r_conn4 = await client.post("/api/v1/tenants/utrecht/apps/utrecht-worker/connect-service", json={
                "service_name": "main-mysql",
            })
            r_conn5 = await client.post("/api/v1/tenants/utrecht/apps/utrecht-worker/connect-service", json={
                "service_name": "task-queue",
            })
            assert r_conn4.status_code == 200
            assert r_conn5.status_code == 200

            # === STEP 5: Verify isolation ===
            # Rotterdam should NOT see Amsterdam's services
            rot_svc_names = {s["name"] for s in rot_svcs.json()}
            ams_svc_names = {s["name"] for s in ams_svcs.json()}
            utr_svc_names = {s["name"] for s in utr_svcs.json()}
            assert rot_svc_names == {"main-pg", "cache"}
            assert ams_svc_names == {"main-mongo", "cache"}
            assert utr_svc_names == {"main-mysql", "task-queue"}

            # Apps are scoped to their tenant
            rot_apps = await client.get("/api/v1/tenants/rotterdam/apps")
            ams_apps = await client.get("/api/v1/tenants/amsterdam/apps")
            utr_apps = await client.get("/api/v1/tenants/utrecht/apps")
            assert {a["slug"] for a in rot_apps.json()} == {"rotterdam-api"}
            assert {a["slug"] for a in ams_apps.json()} == {"amsterdam-portal"}
            assert {a["slug"] for a in utr_apps.json()} == {"utrecht-worker"}

            # === STEP 6: Delete all tenants ===
            d1 = await client.delete("/api/v1/tenants/rotterdam")
            d2 = await client.delete("/api/v1/tenants/amsterdam")
            d3 = await client.delete("/api/v1/tenants/utrecht")
            assert d1.status_code == 204
            assert d2.status_code == 204
            assert d3.status_code == 204

            # === STEP 7: Verify complete cleanup ===
            # No tenants remain
            final_tenants = await client.get("/api/v1/tenants")
            assert len(final_tenants.json()) == 0

            # No apps remain in DB
            result_apps = await db.execute(select(Application))
            assert list(result_apps.scalars()) == []

            # No services remain in DB
            result_svcs = await db.execute(select(ManagedService))
            assert list(result_svcs.scalars()) == []

            # 3 namespaces deleted
            ns_delete_calls = k8s_mock.core_v1.delete_namespace.call_args_list
            deleted_ns = {c.args[0] for c in ns_delete_calls}
            assert "tenant-rotterdam" in deleted_ns
            assert "tenant-amsterdam" in deleted_ns
            assert "tenant-utrecht" in deleted_ns

            # 3 ApplicationSets deleted
            all_delete_calls = k8s_mock.custom_objects.delete_namespaced_custom_object.call_args_list
            appset_deletes = {
                c.kwargs["name"] for c in all_delete_calls
                if c.kwargs.get("plural") == "applicationsets"
            }
            assert "appset-rotterdam" in appset_deletes
            assert "appset-amsterdam" in appset_deletes
            assert "appset-utrecht" in appset_deletes
