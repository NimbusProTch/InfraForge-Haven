"""Tests for BackupService (Sprint I-9: MinIO S3 backup)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.backup_service import (
    _BUCKET_NAME,
    BackupItem,
    BackupService,
    RestoreRequest,
    ServiceType,
    _cnpg_backup_body,
    _cnpg_restore_body,
    _mongodb_backup_body,
    _mysql_backup_body,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_k8s(available: bool = True, list_items: list | None = None) -> MagicMock:
    """Build a mock K8sClient."""
    k8s = MagicMock()
    k8s.is_available.return_value = available
    k8s.custom_objects = MagicMock()
    k8s.custom_objects.list_namespaced_custom_object.return_value = {
        "items": list_items or []
    }
    k8s.custom_objects.create_namespaced_custom_object.return_value = {}
    return k8s


def _backup_item_dict(name: str, phase: str = "completed") -> dict:
    """Minimal CNPG Backup CRD object."""
    return {
        "metadata": {"name": name},
        "status": {
            "phase": phase,
            "startedAt": "2026-01-01T02:00:00Z",
            "stoppedAt": "2026-01-01T02:05:00Z",
            "size": "512Mi",
        },
    }


# ---------------------------------------------------------------------------
# list_backups
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_backups_returns_empty_when_k8s_unavailable():
    k8s = _make_k8s(available=False)
    svc = BackupService(k8s)
    result = await svc.list_backups("utrecht", "utrecht-pg", ServiceType.POSTGRES)
    assert result == []
    k8s.custom_objects.list_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_list_backups_returns_items():
    items = [_backup_item_dict("backup-pg-20260101-020000"), _backup_item_dict("backup-pg-20260102-020000")]
    k8s = _make_k8s(available=True, list_items=items)
    svc = BackupService(k8s)

    result = await svc.list_backups("utrecht", "utrecht-pg", ServiceType.POSTGRES)

    assert len(result) == 2
    assert all(isinstance(b, BackupItem) for b in result)
    assert result[0].phase == "completed"
    assert result[0].service_name == "utrecht-pg"
    assert result[0].service_type == ServiceType.POSTGRES


@pytest.mark.asyncio
async def test_list_backups_s3_path_format():
    k8s = _make_k8s(available=True, list_items=[_backup_item_dict("bkp-1")])
    svc = BackupService(k8s)

    result = await svc.list_backups("gemeente-x", "gx-pg", ServiceType.POSTGRES)

    assert result[0].s3_path == f"s3://{_BUCKET_NAME}/gemeente-x/postgres/gx-pg"


@pytest.mark.asyncio
async def test_list_backups_sorted_newest_first():
    def _override(tag: str, started: str) -> dict:
        d = _backup_item_dict(tag)
        d["status"] = {**d["status"], "startedAt": started}
        return d

    items = [
        _override("old", "2026-01-01T00:00:00Z"),
        _override("new", "2026-01-03T00:00:00Z"),
        _override("mid", "2026-01-02T00:00:00Z"),
    ]
    k8s = _make_k8s(available=True, list_items=items)
    svc = BackupService(k8s)

    result = await svc.list_backups("t", "svc", ServiceType.POSTGRES)

    assert result[0].started_at == "2026-01-03T00:00:00Z"
    assert result[-1].started_at == "2026-01-01T00:00:00Z"


@pytest.mark.asyncio
async def test_list_backups_k8s_exception_returns_empty():
    k8s = _make_k8s(available=True)
    k8s.custom_objects.list_namespaced_custom_object.side_effect = Exception("API error")
    svc = BackupService(k8s)

    result = await svc.list_backups("t", "svc", ServiceType.POSTGRES)

    assert result == []


# ---------------------------------------------------------------------------
# trigger_backup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_backup_returns_name():
    k8s = _make_k8s(available=True)
    svc = BackupService(k8s)

    name = await svc.trigger_backup("utrecht", "utrecht-pg", ServiceType.POSTGRES)

    assert name.startswith("backup-utrecht-pg-")
    k8s.custom_objects.create_namespaced_custom_object.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_backup_unavailable_raises():
    k8s = _make_k8s(available=False)
    svc = BackupService(k8s)

    with pytest.raises(RuntimeError, match="not available"):
        await svc.trigger_backup("t", "svc", ServiceType.POSTGRES)


@pytest.mark.asyncio
async def test_trigger_backup_mysql():
    k8s = _make_k8s(available=True)
    svc = BackupService(k8s)

    name = await svc.trigger_backup("t", "t-mysql", ServiceType.MYSQL)

    assert name.startswith("backup-t-mysql-")
    call_kwargs = k8s.custom_objects.create_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["group"] == "pxc.percona.com"


@pytest.mark.asyncio
async def test_trigger_backup_mongodb():
    k8s = _make_k8s(available=True)
    svc = BackupService(k8s)

    name = await svc.trigger_backup("t", "t-mongo", ServiceType.MONGODB)

    assert name.startswith("backup-t-mongo-")
    call_kwargs = k8s.custom_objects.create_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["group"] == "psmdb.percona.com"


@pytest.mark.asyncio
async def test_trigger_backup_k8s_error_raises():
    k8s = _make_k8s(available=True)
    k8s.custom_objects.create_namespaced_custom_object.side_effect = Exception("conflict")
    svc = BackupService(k8s)

    with pytest.raises(RuntimeError, match="Backup trigger failed"):
        await svc.trigger_backup("t", "svc", ServiceType.POSTGRES)


# ---------------------------------------------------------------------------
# restore_backup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_backup_postgres_creates_cluster():
    k8s = _make_k8s(available=True)
    svc = BackupService(k8s)

    req = RestoreRequest(
        tenant_slug="utrecht",
        service_name="utrecht-pg",
        service_type=ServiceType.POSTGRES,
        backup_id="backup-utrecht-pg-20260101-020000",
    )
    restore_name = await svc.restore_backup(req)

    assert restore_name.startswith("utrecht-pg-restore-")
    call_kwargs = k8s.custom_objects.create_namespaced_custom_object.call_args.kwargs
    assert call_kwargs["group"] == "postgresql.cnpg.io"
    assert call_kwargs["plural"] == "clusters"


@pytest.mark.asyncio
async def test_restore_backup_with_pitr():
    k8s = _make_k8s(available=True)
    svc = BackupService(k8s)

    req = RestoreRequest(
        tenant_slug="t",
        service_name="t-pg",
        service_type=ServiceType.POSTGRES,
        backup_id="bkp-1",
        target_time="2026-01-15T10:00:00Z",
    )
    restore_name = await svc.restore_backup(req)

    assert restore_name.startswith("t-pg-restore-")
    body = k8s.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
    recovery = body["spec"]["bootstrap"]["recovery"]
    assert recovery["recoveryTarget"]["targetTime"] == "2026-01-15T10:00:00Z"


@pytest.mark.asyncio
async def test_restore_unavailable_raises():
    k8s = _make_k8s(available=False)
    svc = BackupService(k8s)

    req = RestoreRequest("t", "svc", ServiceType.POSTGRES, "bkp-1")
    with pytest.raises(RuntimeError, match="not available"):
        await svc.restore_backup(req)


# ---------------------------------------------------------------------------
# CRD body builders
# ---------------------------------------------------------------------------


def test_cnpg_backup_body_structure():
    body = _cnpg_backup_body("bkp-1", "pg-cluster", "cnpg-system")
    assert body["kind"] == "Backup"
    assert body["spec"]["method"] == "barmanObjectStore"
    assert body["spec"]["cluster"]["name"] == "pg-cluster"


def test_cnpg_restore_body_includes_source():
    body = _cnpg_restore_body(
        cluster_name="pg-restore",
        namespace="cnpg-system",
        source_cluster="original-cluster",
        tenant_slug="t",
        service_name="t-pg",
        target_time=None,
    )
    assert body["kind"] == "Cluster"
    ext = body["spec"]["externalClusters"][0]
    assert ext["name"] == "original-cluster"
    assert f"s3://{_BUCKET_NAME}/t/postgres/t-pg" in ext["barmanObjectStore"]["destinationPath"]


def test_mysql_backup_body_structure():
    body = _mysql_backup_body("bkp-mysql", "my-cluster", "ns")
    assert body["kind"] == "PerconaXtraDBClusterBackup"
    assert body["spec"]["pxcCluster"] == "my-cluster"


def test_mongodb_backup_body_structure():
    body = _mongodb_backup_body("bkp-mongo", "mongo-cluster", "ns")
    assert body["kind"] == "PerconaServerMongoDBBackup"
    assert body["spec"]["clusterName"] == "mongo-cluster"


# ---------------------------------------------------------------------------
# s3_path
# ---------------------------------------------------------------------------


def test_s3_path_format():
    path = BackupService.s3_path("utrecht", ServiceType.POSTGRES, "utrecht-pg")
    assert path == f"s3://{_BUCKET_NAME}/utrecht/postgres/utrecht-pg"


def test_s3_path_mysql():
    path = BackupService.s3_path("x", ServiceType.MYSQL, "x-mysql")
    assert path == f"s3://{_BUCKET_NAME}/x/mysql/x-mysql"
