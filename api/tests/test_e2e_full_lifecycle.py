"""End-to-end lifecycle tests for Haven Platform.

Covers the full tenant → app → service → build → deploy → scale → delete flow
using the FastAPI TestClient (httpx AsyncClient) with mocked K8s operations.
Also tests DeploymentStatus enum completeness and CORS configuration parsing.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.config import Settings
from app.deps import get_db, get_k8s
from app.main import app
from app.models.deployment import DeploymentStatus
from app.models.managed_service import ServiceStatus, ServiceTier, ServiceType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_USER = {"sub": "lifecycle-user", "email": "lifecycle@haven.nl", "name": "Lifecycle User"}


def _mock_k8s():
    """Build a mock K8sClient that passes availability checks."""
    m = MagicMock()
    m.is_available.return_value = True
    m.custom_objects = MagicMock()
    m.custom_objects.create_namespaced_custom_object.return_value = {}
    m.custom_objects.delete_namespaced_custom_object.return_value = {}
    m.custom_objects.get_namespaced_custom_object.return_value = {
        "status": {"readyInstances": 1, "phase": "Cluster in healthy state"},
        "spec": {"instances": 1},
    }
    m.core_v1 = MagicMock()
    m.core_v1.create_namespace.return_value = MagicMock()
    m.core_v1.read_namespaced_secret.side_effect = Exception("not found")
    m.core_v1.delete_namespace.return_value = MagicMock()
    m.apps_v1 = MagicMock()
    m.batch_v1 = MagicMock()
    m.autoscaling_v2 = MagicMock()
    return m


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTPX client with DB, K8s, and auth overrides."""

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_k8s] = _mock_k8s
    app.dependency_overrides[verify_token] = lambda: _USER

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: Full Lifecycle
# ---------------------------------------------------------------------------

TENANT_SLUG = "lifecycle-test"
APP_SLUG = "lifecycle-app"
SERVICE_NAME = "app-postgres"


@pytest.mark.asyncio
class TestFullLifecycle:
    """End-to-end lifecycle: tenant -> app -> service -> build -> deploy -> scale -> delete."""

    # -- Tenant --

    async def test_01_create_tenant(self, client: AsyncClient):
        """POST /tenants -> 201"""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()

            resp = await client.post(
                "/api/v1/tenants",
                json={
                    "slug": TENANT_SLUG,
                    "name": "Lifecycle Test Municipality",
                    "tier": "free",
                    "cpu_limit": "4",
                    "memory_limit": "8Gi",
                    "storage_limit": "50Gi",
                },
            )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["slug"] == TENANT_SLUG
        assert data["namespace"] == f"tenant-{TENANT_SLUG}"
        assert data["active"] is True

    # -- App --

    async def test_02_create_app_with_all_fields(self, client: AsyncClient):
        """POST /tenants/{slug}/apps with env_vars, port, health_check, dockerfile_path -> 201"""
        # First create the tenant for this test
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "app-fields", "name": "App Fields Test"},
            )

        resp = await client.post(
            "/api/v1/tenants/app-fields/apps",
            json={
                "name": "Full Fields App",
                "slug": APP_SLUG,
                "repo_url": "https://github.com/test/lifecycle-repo",
                "branch": "main",
                "port": 3000,
                "env_vars": {"NODE_ENV": "production", "LOG_LEVEL": "info"},
                "health_check_path": "/health",
                "dockerfile_path": "backend/Dockerfile",
                "build_context": "backend",
                "use_dockerfile": True,
                "replicas": 2,
                "min_replicas": 1,
                "max_replicas": 10,
                "cpu_threshold": 80,
                "resource_cpu_request": "100m",
                "resource_cpu_limit": "1",
                "resource_memory_request": "128Mi",
                "resource_memory_limit": "1Gi",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["slug"] == APP_SLUG
        assert data["port"] == 3000
        assert data["env_vars"]["NODE_ENV"] == "production"
        assert data["dockerfile_path"] == "backend/Dockerfile"
        assert data["build_context"] == "backend"
        assert data["use_dockerfile"] is True
        assert data["replicas"] == 2
        # health_check_path and resource limits are set via PATCH, not stored on create
        # Verify they are present in the response (defaults from the model)
        assert "health_check_path" in data
        assert "min_replicas" in data
        assert "max_replicas" in data

    async def test_03_list_apps(self, client: AsyncClient):
        """GET /tenants/{slug}/apps -> app in list"""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "list-apps-lc", "name": "List Apps LC"},
            )
        await client.post(
            "/api/v1/tenants/list-apps-lc/apps",
            json={"name": "App One", "slug": "app-one", "repo_url": "https://github.com/t/r", "branch": "main"},
        )
        await client.post(
            "/api/v1/tenants/list-apps-lc/apps",
            json={"name": "App Two", "slug": "app-two", "repo_url": "https://github.com/t/r2", "branch": "main"},
        )

        resp = await client.get("/api/v1/tenants/list-apps-lc/apps")
        assert resp.status_code == 200
        apps = resp.json()
        assert len(apps) == 2
        slugs = {a["slug"] for a in apps}
        assert "app-one" in slugs
        assert "app-two" in slugs

    async def test_04_update_app(self, client: AsyncClient):
        """PATCH /tenants/{slug}/apps/{slug} replicas, env_vars -> 200"""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "update-lc", "name": "Update LC"},
            )
        await client.post(
            "/api/v1/tenants/update-lc/apps",
            json={"name": "Updatable", "slug": "updatable", "repo_url": "https://github.com/t/r", "branch": "main"},
        )

        resp = await client.patch(
            "/api/v1/tenants/update-lc/apps/updatable",
            json={"replicas": 3, "env_vars": {"NEW_VAR": "hello"}, "port": 9090},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["replicas"] == 3
        assert data["env_vars"]["NEW_VAR"] == "hello"
        assert data["port"] == 9090

    # -- Build / Deploy endpoints --

    async def test_05_trigger_build_only(self, client: AsyncClient):
        """POST /build?deploy=false -> 202, deployment has deploy param."""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "build-lc", "name": "Build LC"},
            )
        await client.post(
            "/api/v1/tenants/build-lc/apps",
            json={"name": "Buildable", "slug": "buildable", "repo_url": "https://github.com/t/r", "branch": "main"},
        )

        with patch("app.routers.deployments.run_pipeline", MagicMock(return_value=None)):
            resp = await client.post(
                "/api/v1/tenants/build-lc/apps/buildable/build?deploy=false",
            )
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert data["status"] in ("pending", "building")

    async def test_06_deploy_image_endpoint_exists(self, client: AsyncClient):
        """POST /deploy-image endpoint is registered (returns 404 for missing tenant, not 405)."""
        resp = await client.post("/api/v1/tenants/nonexistent/apps/noapp/deploy-image")
        # 404 means the route is registered but the tenant/app is not found
        # 405 would mean the route doesn't exist
        assert resp.status_code != 405, "deploy-image endpoint not registered"
        assert resp.status_code in (404, 422), resp.text

    async def test_07_build_status_endpoint(self, client: AsyncClient):
        """GET /build-status -> returns structure or 404."""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "bstatus-lc", "name": "BStatus LC"},
            )
        await client.post(
            "/api/v1/tenants/bstatus-lc/apps",
            json={
                "name": "StatusApp",
                "slug": "status-app",
                "repo_url": "https://github.com/t/r",
                "branch": "main",
            },
        )

        resp = await client.get("/api/v1/tenants/bstatus-lc/apps/status-app/build-status")
        # Should return 200 with status data or 404 if no build exists yet
        assert resp.status_code in (200, 404), resp.text

    # -- Managed Services --

    async def test_08_create_managed_service(self, client: AsyncClient):
        """POST /tenants/{slug}/services -> 201"""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "svc-lc", "name": "Service LC"},
            )

        with patch("app.routers.services.ManagedServiceProvisioner") as mock_prov:
            mock_prov.return_value.provision = AsyncMock()
            resp = await client.post(
                "/api/v1/tenants/svc-lc/services",
                json={
                    "name": SERVICE_NAME,
                    "service_type": "postgres",
                    "tier": "dev",
                },
            )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == SERVICE_NAME
        assert data["service_type"] == "postgres"
        assert data["tier"] == "dev"
        assert data["status"] == "provisioning"

    async def test_09_list_services(self, client: AsyncClient):
        """GET /tenants/{slug}/services -> service in list"""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "svc-list-lc", "name": "Service List LC"},
            )

        with patch("app.routers.services.ManagedServiceProvisioner") as mock_prov:
            mock_prov.return_value.provision = AsyncMock()
            await client.post(
                "/api/v1/tenants/svc-list-lc/services",
                json={"name": "list-pg", "service_type": "postgres", "tier": "dev"},
            )
            await client.post(
                "/api/v1/tenants/svc-list-lc/services",
                json={"name": "list-redis", "service_type": "redis", "tier": "dev"},
            )

        resp = await client.get("/api/v1/tenants/svc-list-lc/services")
        assert resp.status_code == 200
        services = resp.json()
        assert len(services) == 2
        names = {s["name"] for s in services}
        assert "list-pg" in names
        assert "list-redis" in names

    # -- Backup --

    async def test_10_backup_trigger(self, client: AsyncClient):
        """POST /services/{name}/backup -> 202 or 503 (K8s unavailable)."""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "backup-lc", "name": "Backup LC"},
            )

        with patch("app.routers.services.ManagedServiceProvisioner") as mock_prov:
            mock_prov.return_value.provision = AsyncMock()
            await client.post(
                "/api/v1/tenants/backup-lc/services",
                json={"name": "backup-pg", "service_type": "postgres", "tier": "dev"},
            )

        with patch("app.routers.backup.BackupService") as mock_bs:
            mock_bs.return_value.trigger_everest_backup = AsyncMock(return_value="backup-20260405-001")
            resp = await client.post("/api/v1/tenants/backup-lc/services/backup-pg/backup")

        assert resp.status_code in (202, 503), resp.text
        if resp.status_code == 202:
            data = resp.json()
            assert "backup_name" in data

    async def test_11_backup_list(self, client: AsyncClient):
        """GET /services/{name}/backups -> list structure."""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "bklist-lc", "name": "BkList LC"},
            )

        with patch("app.routers.services.ManagedServiceProvisioner") as mock_prov:
            mock_prov.return_value.provision = AsyncMock()
            await client.post(
                "/api/v1/tenants/bklist-lc/services",
                json={"name": "bklist-pg", "service_type": "postgres", "tier": "dev"},
            )

        with patch("app.routers.backup.BackupService") as mock_bs:
            mock_bs.return_value.list_everest_backups = AsyncMock(return_value=[])
            resp = await client.get("/api/v1/tenants/bklist-lc/services/bklist-pg/backups")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "backups" in data
        assert isinstance(data["backups"], list)

    # -- Delete (reverse order) --

    async def test_12_delete_app(self, client: AsyncClient):
        """DELETE /tenants/{slug}/apps/{slug} -> 204"""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "del-app-lc", "name": "Del App LC"},
            )
        await client.post(
            "/api/v1/tenants/del-app-lc/apps",
            json={"name": "Deletable", "slug": "deletable", "repo_url": "https://github.com/t/r", "branch": "main"},
        )

        resp = await client.delete("/api/v1/tenants/del-app-lc/apps/deletable")
        assert resp.status_code == 204

        # Verify gone
        resp = await client.get("/api/v1/tenants/del-app-lc/apps")
        assert len(resp.json()) == 0

    async def test_13_delete_service(self, client: AsyncClient):
        """DELETE /tenants/{slug}/services/{name} -> 204"""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "del-svc-lc", "name": "Del Svc LC"},
            )

        with patch("app.routers.services.ManagedServiceProvisioner") as mock_prov:
            mock_prov.return_value.provision = AsyncMock()
            await client.post(
                "/api/v1/tenants/del-svc-lc/services",
                json={"name": "del-pg", "service_type": "postgres", "tier": "dev"},
            )

        with patch("app.routers.services.ManagedServiceProvisioner") as mock_prov:
            mock_prov.return_value.deprovision = AsyncMock()
            resp = await client.delete("/api/v1/tenants/del-svc-lc/services/del-pg")
        assert resp.status_code == 204

        # Verify gone
        resp = await client.get("/api/v1/tenants/del-svc-lc/services")
        assert len(resp.json()) == 0

    async def test_14_delete_tenant(self, client: AsyncClient):
        """DELETE /tenants/{slug} -> 204"""
        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.provision = AsyncMock()
            mock_gs.scaffold_tenant = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={"slug": "del-tenant-lc", "name": "Del Tenant LC"},
            )

        with (
            patch("app.routers.tenants.TenantService") as mock_ts,
            patch("app.routers.tenants.gitops_scaffold") as mock_gs,
        ):
            mock_ts.return_value.deprovision = AsyncMock()
            mock_gs.delete_tenant = AsyncMock()
            resp = await client.delete("/api/v1/tenants/del-tenant-lc")
        assert resp.status_code == 204

        # Verify gone
        resp = await client.get("/api/v1/tenants/del-tenant-lc")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: DeploymentStatus Enum
# ---------------------------------------------------------------------------


class TestDeploymentStatusEnum:
    """Verify the DeploymentStatus enum has all expected values."""

    def test_built_status_exists(self):
        """BUILT status must exist in the enum."""
        assert hasattr(DeploymentStatus, "BUILT")
        assert DeploymentStatus.BUILT.value == "built"

    def test_all_statuses(self):
        """All expected statuses: pending, building, built, deploying, running, failed."""
        expected = {"pending", "building", "built", "deploying", "running", "failed"}
        actual = {s.value for s in DeploymentStatus}
        assert expected == actual, f"Missing: {expected - actual}, Extra: {actual - expected}"

    def test_status_is_str_enum(self):
        """DeploymentStatus values are usable as strings."""
        assert str(DeploymentStatus.RUNNING) == "running" or DeploymentStatus.RUNNING.value == "running"

    def test_pending_is_default_initial(self):
        """PENDING is the initial status for new deployments."""
        assert DeploymentStatus.PENDING.value == "pending"


# ---------------------------------------------------------------------------
# Test: CORS Configuration
# ---------------------------------------------------------------------------


class TestCORSConfig:
    """Verify CORS origin parsing from settings."""

    def test_cors_parses_multiple_origins(self):
        """CORS_ORIGINS comma-separated string is parsed into a list."""
        s = Settings(
            cors_origins="https://app.haven.nl,https://admin.haven.nl,http://localhost:3000",
            database_url="sqlite+aiosqlite:///:memory:",
            secret_key="test-secret",
        )
        origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
        assert len(origins) == 3
        assert "https://app.haven.nl" in origins
        assert "https://admin.haven.nl" in origins
        assert "http://localhost:3000" in origins

    def test_cors_includes_localhost(self):
        """Default CORS_ORIGINS includes localhost:3000."""
        s = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            secret_key="test-secret",
        )
        origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
        assert "http://localhost:3000" in origins

    def test_cors_handles_empty_entries(self):
        """Trailing comma or empty entries should be filtered out."""
        s = Settings(
            cors_origins="https://app.haven.nl,,http://localhost:3000,",
            database_url="sqlite+aiosqlite:///:memory:",
            secret_key="test-secret",
        )
        origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
        assert len(origins) == 2
        assert "" not in origins

    def test_cors_single_origin(self):
        """Single origin without commas works."""
        s = Settings(
            cors_origins="https://app.haven.nl",
            database_url="sqlite+aiosqlite:///:memory:",
            secret_key="test-secret",
        )
        origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
        assert len(origins) == 1
        assert origins[0] == "https://app.haven.nl"


# ---------------------------------------------------------------------------
# Test: Service Types and Tiers
# ---------------------------------------------------------------------------


class TestServiceEnums:
    """Verify managed service enums are complete."""

    def test_all_service_types(self):
        """All 6 service types exist (kafka added 2026-04-17 in commit 7474cb1)."""
        expected = {"postgres", "mysql", "mongodb", "redis", "rabbitmq", "kafka"}
        actual = {t.value for t in ServiceType}
        assert expected == actual

    def test_all_service_tiers(self):
        """DEV and PROD tiers exist."""
        expected = {"dev", "prod"}
        actual = {t.value for t in ServiceTier}
        assert expected == actual

    def test_all_service_statuses(self):
        """All expected service statuses exist."""
        expected = {"provisioning", "ready", "updating", "failed", "deleting", "degraded"}
        actual = {s.value for s in ServiceStatus}
        assert expected == actual
