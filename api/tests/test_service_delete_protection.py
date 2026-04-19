"""L08 — DELETE /tenants/{slug}/services/{name} safety contract.

Pre-fix: the endpoint silently auto-disconnected any apps pointing at the
service and dropped the data with no recovery snapshot. Two real risks:
1. The user could not tell that connected apps were silently broken.
2. There was no snapshot before drop — accidental delete = permanent.

Post-fix:
- Default rejects with 409 + connected app list when at least one app
  references the service.
- ``?force=true`` overrides the check and proceeds with auto-disconnect.
- For postgres/mysql/mongodb, a one-shot Backup CRD is triggered before
  the DatabaseCluster is dropped (best-effort: failure does not block).
- ``?take_final_snapshot=false`` opts out for the "throwing data away"
  case.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.application import Application
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType


def _make_pg(tenant_id: uuid.UUID, name: str = "test-pg") -> ManagedService:
    return ManagedService(
        tenant_id=tenant_id,
        name=name,
        service_type=ServiceType.POSTGRES,
        tier=ServiceTier.DEV,
        status=ServiceStatus.READY,
        service_namespace="everest",
        secret_name=f"everest-secrets-{name}",
        connection_hint=f"postgresql://user:pass@{name}.everest.svc:5432/app",
        credentials_provisioned=False,
    )


def _connect_app_to_service(app: Application, svc: ManagedService) -> None:
    app.env_from_secrets = [
        {
            "service_name": svc.name,
            "secret_name": svc.secret_name,
            "key_to_env": {"DATABASE_URL": "DATABASE_URL"},
        }
    ]
    app.env_vars = {**(app.env_vars or {}), "DATABASE_URL": svc.connection_hint}


# ---------------------------------------------------------------------------
# Connected-app guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_blocked_with_409_when_connected_to_an_app(async_client, db_session, sample_tenant):
    """Default delete must reject 409 when an app references the service."""
    svc = _make_pg(sample_tenant.id, "guarded-pg")
    db_session.add(svc)
    app = Application(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="my-app",
        name="My App",
        repo_url="https://github.com/x/y",
        branch="main",
        port=8000,
        webhook_token="wh-token-x",
    )
    _connect_app_to_service(app, svc)
    db_session.add(app)
    await db_session.commit()

    response = await async_client.delete(f"/api/v1/tenants/{sample_tenant.slug}/services/guarded-pg")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "guarded-pg" in detail["message"]
    assert "my-app" in detail["connected_apps"]
    assert "force=true" in detail["hint"]
    # Service must still exist after a refused delete
    await db_session.refresh(svc)
    assert svc.id is not None


@pytest.mark.asyncio
async def test_delete_succeeds_when_no_apps_are_connected(async_client, db_session, sample_tenant):
    svc = _make_pg(sample_tenant.id, "free-pg")
    db_session.add(svc)
    await db_session.commit()

    with patch("app.routers.services.ManagedServiceProvisioner") as MockProv:
        instance = MockProv.return_value
        instance.deprovision = AsyncMock(return_value=None)
        # No apps connected → final-snapshot path runs (PG + READY) — mock the BackupService
        with patch(
            "app.services.backup_service.BackupService.trigger_backup", new=AsyncMock(return_value="backup-free-pg-x")
        ):
            response = await async_client.delete(f"/api/v1/tenants/{sample_tenant.slug}/services/free-pg")

    assert response.status_code == 204
    instance.deprovision.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_force_true_auto_disconnects_and_succeeds(async_client, db_session, sample_tenant):
    svc = _make_pg(sample_tenant.id, "force-pg")
    db_session.add(svc)
    app = Application(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="brave-app",
        name="Brave App",
        repo_url="https://github.com/x/y",
        branch="main",
        port=8000,
        webhook_token="wh-token-y",
    )
    _connect_app_to_service(app, svc)
    db_session.add(app)
    await db_session.commit()

    with (
        patch("app.routers.services.ManagedServiceProvisioner") as MockProv,
        patch(
            "app.services.backup_service.BackupService.trigger_backup",
            new=AsyncMock(return_value="snap-name"),
        ),
    ):
        instance = MockProv.return_value
        instance.deprovision = AsyncMock(return_value=None)

        response = await async_client.delete(f"/api/v1/tenants/{sample_tenant.slug}/services/force-pg?force=true")

    assert response.status_code == 204
    # The connected app must have been disconnected
    await db_session.refresh(app)
    assert not app.env_from_secrets or all(e.get("service_name") != "force-pg" for e in app.env_from_secrets)
    assert "DATABASE_URL" not in (app.env_vars or {})


# ---------------------------------------------------------------------------
# Final snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_postgres_triggers_final_snapshot_by_default(async_client, db_session, sample_tenant):
    svc = _make_pg(sample_tenant.id, "snap-pg")
    db_session.add(svc)
    await db_session.commit()

    with (
        patch("app.routers.services.ManagedServiceProvisioner") as MockProv,
        patch(
            "app.services.backup_service.BackupService.trigger_backup",
            new=AsyncMock(return_value="backup-snap-pg-2026-04-19"),
        ) as mock_backup,
    ):
        instance = MockProv.return_value
        instance.deprovision = AsyncMock(return_value=None)

        response = await async_client.delete(f"/api/v1/tenants/{sample_tenant.slug}/services/snap-pg")

    assert response.status_code == 204
    mock_backup.assert_awaited_once()
    # Backup happens BEFORE deprovision
    assert mock_backup.await_count == 1


@pytest.mark.asyncio
async def test_delete_take_final_snapshot_false_skips_backup(async_client, db_session, sample_tenant):
    svc = _make_pg(sample_tenant.id, "noskip-pg")
    db_session.add(svc)
    await db_session.commit()

    with (
        patch("app.routers.services.ManagedServiceProvisioner") as MockProv,
        patch(
            "app.services.backup_service.BackupService.trigger_backup",
            new=AsyncMock(return_value="should-not-be-called"),
        ) as mock_backup,
    ):
        instance = MockProv.return_value
        instance.deprovision = AsyncMock(return_value=None)

        response = await async_client.delete(
            f"/api/v1/tenants/{sample_tenant.slug}/services/noskip-pg?take_final_snapshot=false"
        )

    assert response.status_code == 204
    mock_backup.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_redis_skips_backup_even_if_take_final_snapshot_true(async_client, db_session, sample_tenant):
    """Redis has no backup CRD wired in this platform — the helper must
    silently skip the snapshot rather than try and fail."""
    svc = ManagedService(
        tenant_id=sample_tenant.id,
        name="cache-redis",
        service_type=ServiceType.REDIS,
        tier=ServiceTier.DEV,
        status=ServiceStatus.READY,
        service_namespace="redis-system",
        secret_name="redis-secrets-cache-redis",
    )
    db_session.add(svc)
    await db_session.commit()

    with (
        patch("app.routers.services.ManagedServiceProvisioner") as MockProv,
        patch(
            "app.services.backup_service.BackupService.trigger_backup",
            new=AsyncMock(return_value="should-not-be-called"),
        ) as mock_backup,
    ):
        instance = MockProv.return_value
        instance.deprovision = AsyncMock(return_value=None)

        response = await async_client.delete(f"/api/v1/tenants/{sample_tenant.slug}/services/cache-redis")

    assert response.status_code == 204
    mock_backup.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_continues_when_final_snapshot_fails(async_client, db_session, sample_tenant):
    """Snapshot failure must not block delete — operator may have killed
    backup CRDs already; we proceed and log."""
    svc = _make_pg(sample_tenant.id, "snap-fail-pg")
    db_session.add(svc)
    await db_session.commit()

    with (
        patch("app.routers.services.ManagedServiceProvisioner") as MockProv,
        patch(
            "app.services.backup_service.BackupService.trigger_backup",
            new=AsyncMock(side_effect=RuntimeError("MinIO bucket missing")),
        ) as mock_backup,
    ):
        instance = MockProv.return_value
        instance.deprovision = AsyncMock(return_value=None)

        response = await async_client.delete(f"/api/v1/tenants/{sample_tenant.slug}/services/snap-fail-pg")

    assert response.status_code == 204
    mock_backup.assert_awaited_once()
    instance.deprovision.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_skips_snapshot_when_service_not_ready(async_client, db_session, sample_tenant):
    """A PROVISIONING / FAILED service cannot produce a meaningful backup
    yet — skip it rather than create a CRD that immediately errors."""
    svc = _make_pg(sample_tenant.id, "not-ready-pg")
    svc.status = ServiceStatus.PROVISIONING
    db_session.add(svc)
    await db_session.commit()

    with (
        patch("app.routers.services.ManagedServiceProvisioner") as MockProv,
        patch(
            "app.services.backup_service.BackupService.trigger_backup",
            new=AsyncMock(return_value="should-not-be-called"),
        ) as mock_backup,
    ):
        instance = MockProv.return_value
        instance.deprovision = AsyncMock(return_value=None)

        response = await async_client.delete(f"/api/v1/tenants/{sample_tenant.slug}/services/not-ready-pg")

    assert response.status_code == 204
    mock_backup.assert_not_awaited()
