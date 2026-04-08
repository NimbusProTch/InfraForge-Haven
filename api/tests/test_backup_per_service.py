"""Tests for per-service backup/restore endpoints (Sprint E2).

Tests:
- List backups per service (PG, MySQL, MongoDB)
- Trigger backup per service
- Restore from backup
- Error cases (unknown service, unsupported type, K8s unavailable)
- MySQL/MongoDB restore CRD body builders
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
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier
from app.models.managed_service import ServiceType as ModelServiceType
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.services.backup_service import (
    BackupService,
    RestoreRequest,
    ServiceType,
    _mongodb_restore_body,
    _mysql_restore_body,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _make_tenant(db: AsyncSession, slug: str = "bkp-test", add_test_user: bool = True) -> Tenant:
    """Create a tenant with test-user as owner so per-service backup
    endpoints (which now enforce membership) succeed by default.
    """
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        name=f"Backup {slug}",
        namespace=f"tenant-{slug}",
        keycloak_realm=slug,
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(tenant)
    await db.flush()
    if add_test_user:
        member = TenantMember(
            tenant_id=tenant.id,
            user_id="test-user",
            email="test@haven.nl",
            role=MemberRole("owner"),
        )
        db.add(member)
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def _make_service(
    db: AsyncSession,
    tenant: Tenant,
    name: str = "app-pg",
    svc_type: ModelServiceType = ModelServiceType.POSTGRES,
    everest_name: str | None = None,
) -> ManagedService:
    svc = ManagedService(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name=name,
        service_type=svc_type,
        tier=ServiceTier.DEV,
        status=ServiceStatus.READY,
        secret_name=f"svc-{name}",
        service_namespace="everest",
        everest_name=everest_name or f"{tenant.slug}-{name}",
        credentials_provisioned=True,
    )
    db.add(svc)
    await db.commit()
    await db.refresh(svc)
    return svc


def _mock_k8s(available: bool = True, list_items: list | None = None) -> MagicMock:
    mock = MagicMock()
    mock.is_available.return_value = available
    mock.custom_objects = MagicMock()
    mock.custom_objects.list_namespaced_custom_object.return_value = {"items": list_items or []}
    mock.custom_objects.create_namespaced_custom_object.return_value = {}
    return mock


@pytest_asyncio.fixture
async def k8s_client_with_backups(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async client with K8s available and sample backup items."""
    mock_k8s = _mock_k8s(
        available=True,
        list_items=[
            {
                "metadata": {"name": "backup-app-pg-20260401-020000"},
                "status": {
                    "state": "Succeeded",
                    "created": "2026-04-01T02:00:00Z",
                    "completed": "2026-04-01T02:05:00Z",
                    "destination": "s3://haven-backups/test/pg",
                },
            },
        ],
    )

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test-user", "email": "test@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def k8s_client_no_k8s(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async client with K8s unavailable."""
    mock_k8s = _mock_k8s(available=False)

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test-user", "email": "test@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# List backups per service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pg_backups(k8s_client_with_backups, db_session):
    """GET /tenants/{slug}/services/{name}/backups returns PG backups."""
    tenant = await _make_tenant(db_session)
    await _make_service(db_session, tenant, "app-pg", ModelServiceType.POSTGRES)

    response = await k8s_client_with_backups.get(f"/api/v1/tenants/{tenant.slug}/services/app-pg/backups")
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_slug"] == tenant.slug
    assert data["service_name"] == "app-pg"
    assert data["k8s_available"] is True
    assert len(data["backups"]) == 1
    assert data["backups"][0]["phase"] == "Succeeded"


@pytest.mark.asyncio
async def test_list_mysql_backups(k8s_client_with_backups, db_session):
    """GET /tenants/{slug}/services/{name}/backups returns MySQL backups."""
    tenant = await _make_tenant(db_session, "mysql-bkp")
    await _make_service(db_session, tenant, "app-mysql", ModelServiceType.MYSQL)

    response = await k8s_client_with_backups.get(f"/api/v1/tenants/{tenant.slug}/services/app-mysql/backups")
    assert response.status_code == 200
    data = response.json()
    assert data["service_name"] == "app-mysql"


@pytest.mark.asyncio
async def test_list_mongodb_backups(k8s_client_with_backups, db_session):
    """GET /tenants/{slug}/services/{name}/backups returns MongoDB backups."""
    tenant = await _make_tenant(db_session, "mongo-bkp")
    await _make_service(db_session, tenant, "app-mongo", ModelServiceType.MONGODB)

    response = await k8s_client_with_backups.get(f"/api/v1/tenants/{tenant.slug}/services/app-mongo/backups")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_backups_unknown_service_404(k8s_client_with_backups, db_session):
    """GET /backups returns 404 for unknown service."""
    tenant = await _make_tenant(db_session, "unknown-svc")
    response = await k8s_client_with_backups.get(f"/api/v1/tenants/{tenant.slug}/services/nope/backups")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_backups_redis_unsupported(k8s_client_with_backups, db_session):
    """GET /backups returns 400 for Redis (no backup support)."""
    tenant = await _make_tenant(db_session, "redis-bkp")
    await _make_service(db_session, tenant, "app-redis", ModelServiceType.REDIS)

    response = await k8s_client_with_backups.get(f"/api/v1/tenants/{tenant.slug}/services/app-redis/backups")
    assert response.status_code == 400
    assert "not supported" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_backups_k8s_unavailable(k8s_client_no_k8s, db_session):
    """GET /backups returns empty list when K8s unavailable."""
    tenant = await _make_tenant(db_session, "nok8s-bkp")
    await _make_service(db_session, tenant, "app-pg", ModelServiceType.POSTGRES)

    response = await k8s_client_no_k8s.get(f"/api/v1/tenants/{tenant.slug}/services/app-pg/backups")
    assert response.status_code == 200
    data = response.json()
    assert data["k8s_available"] is False
    assert data["backups"] == []


# ---------------------------------------------------------------------------
# Trigger backup per service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_pg_backup(k8s_client_with_backups, db_session):
    """POST /backup triggers PG backup."""
    tenant = await _make_tenant(db_session, "pg-trigger")
    await _make_service(db_session, tenant, "app-pg", ModelServiceType.POSTGRES)

    response = await k8s_client_with_backups.post(f"/api/v1/tenants/{tenant.slug}/services/app-pg/backup")
    assert response.status_code == 202
    data = response.json()
    assert "backup_name" in data
    assert data["backup_name"].startswith("backup-")


@pytest.mark.asyncio
async def test_trigger_mysql_backup(k8s_client_with_backups, db_session):
    """POST /backup triggers MySQL backup."""
    tenant = await _make_tenant(db_session, "mysql-trigger")
    await _make_service(db_session, tenant, "app-mysql", ModelServiceType.MYSQL)

    response = await k8s_client_with_backups.post(f"/api/v1/tenants/{tenant.slug}/services/app-mysql/backup")
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_trigger_mongodb_backup(k8s_client_with_backups, db_session):
    """POST /backup triggers MongoDB backup."""
    tenant = await _make_tenant(db_session, "mongo-trigger")
    await _make_service(db_session, tenant, "app-mongo", ModelServiceType.MONGODB)

    response = await k8s_client_with_backups.post(f"/api/v1/tenants/{tenant.slug}/services/app-mongo/backup")
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_trigger_backup_k8s_unavailable_503(k8s_client_no_k8s, db_session):
    """POST /backup returns 503 when K8s unavailable."""
    tenant = await _make_tenant(db_session, "nok8s-trigger")
    await _make_service(db_session, tenant, "app-pg", ModelServiceType.POSTGRES)

    response = await k8s_client_no_k8s.post(f"/api/v1/tenants/{tenant.slug}/services/app-pg/backup")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_trigger_backup_unknown_service_404(k8s_client_with_backups, db_session):
    """POST /backup returns 404 for unknown service."""
    tenant = await _make_tenant(db_session, "unknown-trigger")
    response = await k8s_client_with_backups.post(f"/api/v1/tenants/{tenant.slug}/services/ghost/backup")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Restore from backup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_pg_backup(k8s_client_with_backups, db_session):
    """POST /restore triggers PG restore."""
    tenant = await _make_tenant(db_session, "pg-restore")
    await _make_service(db_session, tenant, "app-pg", ModelServiceType.POSTGRES)

    response = await k8s_client_with_backups.post(
        f"/api/v1/tenants/{tenant.slug}/services/app-pg/restore/backup-app-pg-20260401"
    )
    assert response.status_code == 202
    data = response.json()
    assert "restore_name" in data
    assert data["restore_name"].startswith(f"{tenant.slug}-app-pg-restore-")


@pytest.mark.asyncio
async def test_restore_pg_with_pitr(k8s_client_with_backups, db_session):
    """POST /restore with target_time triggers PITR restore."""
    tenant = await _make_tenant(db_session, "pg-pitr")
    await _make_service(db_session, tenant, "app-pg", ModelServiceType.POSTGRES)

    response = await k8s_client_with_backups.post(
        f"/api/v1/tenants/{tenant.slug}/services/app-pg/restore/backup-app-pg-20260401",
        json={"target_time": "2026-04-01T02:03:00Z"},
    )
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_restore_mysql_backup(k8s_client_with_backups, db_session):
    """POST /restore triggers MySQL restore via CRD."""
    tenant = await _make_tenant(db_session, "mysql-restore")
    await _make_service(db_session, tenant, "app-mysql", ModelServiceType.MYSQL)

    response = await k8s_client_with_backups.post(
        f"/api/v1/tenants/{tenant.slug}/services/app-mysql/restore/backup-mysql-20260401"
    )
    assert response.status_code == 202
    data = response.json()
    assert "restore_name" in data


@pytest.mark.asyncio
async def test_restore_mongodb_backup(k8s_client_with_backups, db_session):
    """POST /restore triggers MongoDB restore via CRD."""
    tenant = await _make_tenant(db_session, "mongo-restore")
    await _make_service(db_session, tenant, "app-mongo", ModelServiceType.MONGODB)

    response = await k8s_client_with_backups.post(
        f"/api/v1/tenants/{tenant.slug}/services/app-mongo/restore/backup-mongo-20260401"
    )
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_restore_k8s_unavailable_503(k8s_client_no_k8s, db_session):
    """POST /restore returns 503 when K8s unavailable."""
    tenant = await _make_tenant(db_session, "nok8s-restore")
    await _make_service(db_session, tenant, "app-pg", ModelServiceType.POSTGRES)

    response = await k8s_client_no_k8s.post(f"/api/v1/tenants/{tenant.slug}/services/app-pg/restore/backup-20260401")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_restore_unknown_service_404(k8s_client_with_backups, db_session):
    """POST /restore returns 404 for unknown service."""
    tenant = await _make_tenant(db_session, "unknown-restore")
    response = await k8s_client_with_backups.post(
        f"/api/v1/tenants/{tenant.slug}/services/ghost/restore/backup-20260401"
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# CRD body builder tests
# ---------------------------------------------------------------------------


def test_mysql_restore_body_structure():
    """MySQL restore CRD body has correct structure."""
    body = _mysql_restore_body("restore-mysql-001", "test-app-mysql", "everest", "backup-mysql-20260401")
    assert body["apiVersion"] == "pxc.percona.com/v1"
    assert body["kind"] == "PerconaXtraDBClusterRestore"
    assert body["spec"]["pxcCluster"] == "test-app-mysql"
    assert body["spec"]["backupName"] == "backup-mysql-20260401"
    assert body["metadata"]["namespace"] == "everest"


def test_mongodb_restore_body_structure():
    """MongoDB restore CRD body has correct structure."""
    body = _mongodb_restore_body("restore-mongo-001", "test-app-mongo", "everest", "backup-mongo-20260401")
    assert body["apiVersion"] == "psmdb.percona.com/v1"
    assert body["kind"] == "PerconaServerMongoDBRestore"
    assert body["spec"]["clusterName"] == "test-app-mongo"
    assert body["spec"]["backupName"] == "backup-mongo-20260401"


# ---------------------------------------------------------------------------
# BackupService unit tests for restore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backup_service_restore_mysql():
    """BackupService.restore_backup creates MySQL restore CRD."""
    k8s = _mock_k8s()
    svc = BackupService(k8s)

    request = RestoreRequest(
        tenant_slug="test",
        service_name="test-app-mysql",
        service_type=ServiceType.MYSQL,
        backup_id="backup-mysql-20260401",
    )
    name = await svc.restore_backup(request)
    assert name.startswith("test-app-mysql-restore-")
    k8s.custom_objects.create_namespaced_custom_object.assert_called_once()

    call_kwargs = k8s.custom_objects.create_namespaced_custom_object.call_args
    body = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body")
    assert body["kind"] == "PerconaXtraDBClusterRestore"


@pytest.mark.asyncio
async def test_backup_service_restore_mongodb():
    """BackupService.restore_backup creates MongoDB restore CRD."""
    k8s = _mock_k8s()
    svc = BackupService(k8s)

    request = RestoreRequest(
        tenant_slug="test",
        service_name="test-app-mongo",
        service_type=ServiceType.MONGODB,
        backup_id="backup-mongo-20260401",
    )
    name = await svc.restore_backup(request)
    assert name.startswith("test-app-mongo-restore-")
    k8s.custom_objects.create_namespaced_custom_object.assert_called_once()


@pytest.mark.asyncio
async def test_backup_service_restore_k8s_unavailable():
    """BackupService.restore_backup raises when K8s unavailable."""
    k8s = _mock_k8s(available=False)
    svc = BackupService(k8s)

    request = RestoreRequest(
        tenant_slug="test",
        service_name="test-pg",
        service_type=ServiceType.POSTGRES,
        backup_id="backup-20260401",
    )
    with pytest.raises(RuntimeError, match="not available"):
        await svc.restore_backup(request)


@pytest.mark.asyncio
async def test_backup_service_restore_unsupported_type():
    """BackupService.restore_backup raises for unsupported type."""
    k8s = _mock_k8s()
    svc = BackupService(k8s)

    # Redis is not in _RESTORE_CRD or POSTGRES handler
    request = RestoreRequest(
        tenant_slug="test",
        service_name="test-redis",
        service_type="redis",  # type: ignore[arg-type]
        backup_id="backup-20260401",
    )
    with pytest.raises(RuntimeError, match="not supported"):
        await svc.restore_backup(request)


# ---------------------------------------------------------------------------
# H0-2: Per-service cross-tenant isolation regression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_service_backup_cross_tenant_access_denied(async_client, db_session):
    """A non-member must NOT be able to list per-service backups for another tenant."""
    foreign = await _make_tenant(db_session, slug="foreign-svc-bkp", add_test_user=False)
    await _make_service(db_session, foreign, name="app-pg")
    response = await async_client.get(f"/api/v1/tenants/{foreign.slug}/services/app-pg/backups")
    assert response.status_code == 403
    assert "not a member" in response.json()["detail"].lower()
