"""Backup service: MinIO S3 backup listing, trigger, and restore for managed DBs.

Supports:
- PostgreSQL via CNPG Backup / ScheduledBackup CRDs (barman object store)
- MySQL via Percona XtraDB backup CRDs
- MongoDB via Percona MongoDB backup CRDs

All backups are stored in MinIO under:
  s3://haven-backups/{tenant_slug}/{service_type}/{service_name}/
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.k8s.client import K8sClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CNPG_BACKUP_NAMESPACE = "cnpg-system"
_BUCKET_NAME = "haven-backups"
_MINIO_ENDPOINT = "http://minio.minio-system.svc:9000"
_CREDENTIALS_SECRET = "backup-s3-credentials"


class ServiceType(StrEnum):
    POSTGRES = "postgres"
    MYSQL = "mysql"
    MONGODB = "mongodb"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BackupItem:
    backup_id: str
    service_name: str
    service_type: ServiceType
    phase: str  # completed | failed | running
    started_at: str | None
    finished_at: str | None
    size: str | None
    s3_path: str | None


@dataclass
class RestoreRequest:
    tenant_slug: str
    service_name: str
    service_type: ServiceType
    backup_id: str
    target_time: str | None = None  # ISO 8601 for PITR


# ---------------------------------------------------------------------------
# CRD helpers
# ---------------------------------------------------------------------------


def _cnpg_backup_body(backup_name: str, cluster_name: str, namespace: str) -> dict:
    """CNPG on-demand Backup manifest with barman object store."""
    return {
        "apiVersion": "postgresql.cnpg.io/v1",
        "kind": "Backup",
        "metadata": {"name": backup_name, "namespace": namespace},
        "spec": {
            "cluster": {"name": cluster_name},
            "method": "barmanObjectStore",
        },
    }


def _cnpg_restore_body(
    cluster_name: str,
    namespace: str,
    source_cluster: str,
    tenant_slug: str,
    service_name: str,
    target_time: str | None,
) -> dict:
    """CNPG Cluster manifest for point-in-time restore from barman."""
    spec: dict = {
        "instances": 1,
        "storage": {"storageClass": "longhorn", "size": "10Gi"},
        "bootstrap": {
            "recovery": {
                "source": source_cluster,
                **({"recoveryTarget": {"targetTime": target_time}} if target_time else {}),
            }
        },
        "externalClusters": [
            {
                "name": source_cluster,
                "barmanObjectStore": {
                    "destinationPath": f"s3://{_BUCKET_NAME}/{tenant_slug}/postgres/{service_name}",
                    "endpointURL": _MINIO_ENDPOINT,
                    "s3Credentials": {
                        "accessKeyId": {"name": _CREDENTIALS_SECRET, "key": "ACCESS_KEY_ID"},
                        "secretAccessKey": {"name": _CREDENTIALS_SECRET, "key": "ACCESS_SECRET_KEY"},
                    },
                },
            }
        ],
        "affinity": {"tolerations": [{"operator": "Exists"}]},
    }
    return {
        "apiVersion": "postgresql.cnpg.io/v1",
        "kind": "Cluster",
        "metadata": {"name": cluster_name, "namespace": namespace},
        "spec": spec,
    }


def _percona_pg_backup_body(backup_name: str, cluster_name: str, namespace: str) -> dict:
    """Percona PostgreSQL on-demand backup manifest."""
    return {
        "apiVersion": "pgv2.percona.com/v2",
        "kind": "PerconaPGBackup",
        "metadata": {"name": backup_name, "namespace": namespace},
        "spec": {"pgCluster": cluster_name, "repoName": "repo1"},
    }


def _mysql_backup_body(backup_name: str, cluster_name: str, namespace: str) -> dict:
    """Percona XtraDB on-demand backup manifest."""
    return {
        "apiVersion": "pxc.percona.com/v1",
        "kind": "PerconaXtraDBClusterBackup",
        "metadata": {"name": backup_name, "namespace": namespace},
        "spec": {"pxcCluster": cluster_name, "storageName": "minio-backup"},
    }


def _mongodb_backup_body(backup_name: str, cluster_name: str, namespace: str) -> dict:
    """Percona MongoDB on-demand backup manifest."""
    return {
        "apiVersion": "psmdb.percona.com/v1",
        "kind": "PerconaServerMongoDBBackup",
        "metadata": {"name": backup_name, "namespace": namespace},
        "spec": {"clusterName": cluster_name, "storageName": "minio-backup"},
    }


# ---------------------------------------------------------------------------
# CRD config table
# ---------------------------------------------------------------------------

_BACKUP_CRD = {
    ServiceType.POSTGRES: {
        "group": "postgresql.cnpg.io",
        "version": "v1",
        "plural": "backups",
        "namespace_fn": lambda _tenant: _CNPG_BACKUP_NAMESPACE,
        "body_fn": _cnpg_backup_body,
    },
    ServiceType.MYSQL: {
        "group": "pxc.percona.com",
        "version": "v1",
        "plural": "perconaxtradbclusterbackups",
        "namespace_fn": lambda tenant: f"tenant-{tenant}",
        "body_fn": _mysql_backup_body,
    },
    ServiceType.MONGODB: {
        "group": "psmdb.percona.com",
        "version": "v1",
        "plural": "perconaservermongodbbkps",
        "namespace_fn": lambda tenant: f"tenant-{tenant}",
        "body_fn": _mongodb_backup_body,
    },
}

_LIST_CRD = {
    ServiceType.POSTGRES: {
        "group": "postgresql.cnpg.io",
        "version": "v1",
        "plural": "backups",
        "namespace_fn": lambda _tenant: _CNPG_BACKUP_NAMESPACE,
        "label_fn": lambda cluster: f"cnpg.io/cluster={cluster}",
        "phase_key": "phase",
        "started_key": "startedAt",
        "finished_key": "stoppedAt",
        "size_key": "size",
    },
    ServiceType.MYSQL: {
        "group": "pxc.percona.com",
        "version": "v1",
        "plural": "perconaxtradbclusterbackups",
        "namespace_fn": lambda tenant: f"tenant-{tenant}",
        "label_fn": lambda cluster: f"pxc.percona.com/cluster={cluster}",
        "phase_key": "state",
        "started_key": "startTime",
        "finished_key": "completedAt",
        "size_key": None,
    },
    ServiceType.MONGODB: {
        "group": "psmdb.percona.com",
        "version": "v1",
        "plural": "perconaservermongodbbkps",
        "namespace_fn": lambda tenant: f"tenant-{tenant}",
        "label_fn": lambda cluster: f"psmdb.percona.com/cluster={cluster}",
        "phase_key": "state",
        "started_key": "startTime",
        "finished_key": "completedAt",
        "size_key": None,
    },
}


# ---------------------------------------------------------------------------
# BackupService
# ---------------------------------------------------------------------------


class BackupService:
    """Backup operations: list, trigger, restore for managed databases.

    Parameters
    ----------
    k8s:
        An initialized :class:`app.k8s.client.K8sClient` instance.
    """

    def __init__(self, k8s: K8sClient) -> None:
        self.k8s = k8s

    # ------------------------------------------------------------------
    # list_backups
    # ------------------------------------------------------------------

    async def list_backups(
        self,
        tenant_slug: str,
        service_name: str,
        service_type: ServiceType = ServiceType.POSTGRES,
    ) -> list[BackupItem]:
        """List backups for a managed service from K8s CRDs.

        Parameters
        ----------
        tenant_slug:
            Tenant identifier (e.g. ``gemeente-utrecht``).
        service_name:
            Name of the managed service CRD (e.g. ``utrecht-pg``).
        service_type:
            One of :class:`ServiceType`.

        Returns
        -------
        list[BackupItem]
            Sorted newest-first.
        """
        if not self.k8s.is_available():
            logger.warning("K8s unavailable — returning empty backup list")
            return []

        cfg = _LIST_CRD[service_type]
        namespace = cfg["namespace_fn"](tenant_slug)
        label_selector = cfg["label_fn"](service_name)

        try:
            result = await asyncio.to_thread(
                self.k8s.custom_objects.list_namespaced_custom_object,
                group=cfg["group"],
                version=cfg["version"],
                namespace=namespace,
                plural=cfg["plural"],
                label_selector=label_selector,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to list backups for %s/%s", tenant_slug, service_name)
            return []

        items: list[BackupItem] = []
        for obj in result.get("items", []):
            meta = obj.get("metadata", {})
            status = obj.get("status", {})
            s3_path = (
                f"s3://{_BUCKET_NAME}/{tenant_slug}/{service_type.value}/{service_name}"
            )
            items.append(
                BackupItem(
                    backup_id=meta.get("name", ""),
                    service_name=service_name,
                    service_type=service_type,
                    phase=status.get(cfg["phase_key"], "unknown"),
                    started_at=status.get(cfg["started_key"]),
                    finished_at=status.get(cfg["finished_key"]),
                    size=status.get(cfg["size_key"]) if cfg["size_key"] else None,
                    s3_path=s3_path,
                )
            )

        # Sort newest-first by started_at (None values go to end)
        items.sort(key=lambda b: b.started_at or "", reverse=True)
        return items

    # ------------------------------------------------------------------
    # trigger_backup
    # ------------------------------------------------------------------

    async def trigger_backup(
        self,
        tenant_slug: str,
        service_name: str,
        service_type: ServiceType = ServiceType.POSTGRES,
    ) -> str:
        """Trigger an on-demand backup. Returns the backup CRD name."""
        if not self.k8s.is_available():
            raise RuntimeError("Kubernetes cluster not available")

        now = datetime.now(UTC)
        backup_name = f"backup-{service_name}-{now.strftime('%Y%m%d-%H%M%S')}"

        cfg = _BACKUP_CRD[service_type]
        namespace = cfg["namespace_fn"](tenant_slug)
        body = cfg["body_fn"](backup_name, service_name, namespace)

        try:
            await asyncio.to_thread(
                self.k8s.custom_objects.create_namespaced_custom_object,
                group=cfg["group"],
                version=cfg["version"],
                namespace=namespace,
                plural=cfg["plural"],
                body=body,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to trigger backup for %s/%s", tenant_slug, service_name)
            raise RuntimeError(f"Backup trigger failed: {exc}") from exc

        logger.info(
            "Backup triggered: %s/%s type=%s name=%s",
            tenant_slug,
            service_name,
            service_type,
            backup_name,
        )
        return backup_name

    # ------------------------------------------------------------------
    # restore_backup
    # ------------------------------------------------------------------

    async def restore_backup(self, request: RestoreRequest) -> str:
        """Restore a managed database from a backup.

        For PostgreSQL, creates a new CNPG cluster that bootstraps from
        the barman object store. The restored cluster is named
        ``{service_name}-restore-{timestamp}``.

        Parameters
        ----------
        request:
            :class:`RestoreRequest` with all restore parameters.

        Returns
        -------
        str
            Name of the restore resource created in K8s.
        """
        if not self.k8s.is_available():
            raise RuntimeError("Kubernetes cluster not available")

        now = datetime.now(UTC)
        restore_name = f"{request.service_name}-restore-{now.strftime('%Y%m%d-%H%M%S')}"

        if request.service_type == ServiceType.POSTGRES:
            namespace = _CNPG_BACKUP_NAMESPACE
            body = _cnpg_restore_body(
                cluster_name=restore_name,
                namespace=namespace,
                source_cluster=request.backup_id,
                tenant_slug=request.tenant_slug,
                service_name=request.service_name,
                target_time=request.target_time,
            )
            try:
                await asyncio.to_thread(
                    self.k8s.custom_objects.create_namespaced_custom_object,
                    group="postgresql.cnpg.io",
                    version="v1",
                    namespace=namespace,
                    plural="clusters",
                    body=body,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("CNPG restore failed for %s", request.service_name)
                raise RuntimeError(f"Restore failed: {exc}") from exc

        else:
            # MySQL / MongoDB: create a restore CRD (operator-specific)
            # For now we log a warning — full implementation requires
            # operator-specific restore CRDs (PerconaXtraDBClusterRestore, etc.)
            logger.warning(
                "Restore for %s not yet fully implemented via CRD — trigger manually.",
                request.service_type,
            )

        logger.info(
            "Restore initiated: %s/%s backup_id=%s restore=%s",
            request.tenant_slug,
            request.service_name,
            request.backup_id,
            restore_name,
        )
        return restore_name

    # ------------------------------------------------------------------
    # s3_path
    # ------------------------------------------------------------------

    @staticmethod
    def s3_path(tenant_slug: str, service_type: ServiceType, service_name: str) -> str:
        """Return the canonical S3 path for a service's backups."""
        return f"s3://{_BUCKET_NAME}/{tenant_slug}/{service_type.value}/{service_name}"
