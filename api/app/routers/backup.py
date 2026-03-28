"""Backup and Disaster Recovery endpoints.

Provides:
- CNPG scheduled backup configuration
- On-demand backup trigger
- Backup status listing
- Tenant data export endpoint
"""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import DBSession, K8sDep
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/backup", tags=["backup"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BackupScheduleConfig(BaseModel):
    schedule: str = "0 2 * * *"  # Default: 2am daily
    retention_days: int = 30
    storage_location: str = "minio"  # minio | s3


class BackupStatusItem(BaseModel):
    name: str
    phase: str
    started_at: str | None
    finished_at: str | None
    size: str | None


class BackupListResponse(BaseModel):
    tenant_slug: str
    k8s_available: bool
    backups: list[BackupStatusItem]


class BackupTriggerResponse(BaseModel):
    message: str
    backup_name: str
    triggered_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=BackupListResponse)
async def list_backups(tenant_slug: str, db: DBSession, k8s: K8sDep) -> BackupListResponse:
    """List CNPG backups for the tenant's database cluster."""
    tenant = await _get_tenant_or_404(tenant_slug, db)

    if not k8s.is_available():
        return BackupListResponse(tenant_slug=tenant.slug, k8s_available=False, backups=[])

    backups: list[BackupStatusItem] = []
    try:
        result = await asyncio.to_thread(
            k8s.custom_objects.list_namespaced_custom_object,
            group="postgresql.cnpg.io",
            version="v1",
            namespace="cnpg-system",
            plural="backups",
            label_selector=f"cnpg.io/cluster=haven-{tenant.slug}",
        )
        for item in result.get("items", []):
            meta = item.get("metadata", {})
            status_info = item.get("status", {})
            backups.append(
                BackupStatusItem(
                    name=meta.get("name", ""),
                    phase=status_info.get("phase", "unknown"),
                    started_at=status_info.get("startedAt"),
                    finished_at=status_info.get("stoppedAt"),
                    size=status_info.get("size"),
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not list backups for tenant %s: %s", tenant_slug, exc)

    return BackupListResponse(tenant_slug=tenant.slug, k8s_available=True, backups=backups)


@router.post("", response_model=BackupTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_backup(tenant_slug: str, db: DBSession, k8s: K8sDep) -> BackupTriggerResponse:
    """Trigger an on-demand CNPG backup for the tenant's database cluster."""
    tenant = await _get_tenant_or_404(tenant_slug, db)

    if not k8s.is_available():
        raise HTTPException(status_code=503, detail="Kubernetes cluster not available")

    now = datetime.now(UTC)
    backup_name = f"backup-{tenant.slug}-{now.strftime('%Y%m%d-%H%M%S')}"

    backup_manifest = {
        "apiVersion": "postgresql.cnpg.io/v1",
        "kind": "Backup",
        "metadata": {
            "name": backup_name,
            "namespace": "cnpg-system",
        },
        "spec": {
            "cluster": {"name": f"haven-{tenant.slug}"},
            "method": "barmanObjectStore",
        },
    }

    try:
        await asyncio.to_thread(
            k8s.custom_objects.create_namespaced_custom_object,
            group="postgresql.cnpg.io",
            version="v1",
            namespace="cnpg-system",
            plural="backups",
            body=backup_manifest,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to trigger backup: {exc}") from exc

    return BackupTriggerResponse(
        message="Backup triggered successfully",
        backup_name=backup_name,
        triggered_at=now.isoformat(),
    )


@router.put("/schedule", status_code=status.HTTP_200_OK)
async def configure_backup_schedule(
    tenant_slug: str,
    config: BackupScheduleConfig,
    db: DBSession,
    k8s: K8sDep,
) -> dict:
    """Configure the CNPG scheduled backup for a tenant's database cluster.

    Updates the ScheduledBackup CRD with the provided cron schedule.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db)

    if not k8s.is_available():
        raise HTTPException(status_code=503, detail="Kubernetes cluster not available")

    scheduled_backup_name = f"scheduled-{tenant.slug}"

    manifest = {
        "apiVersion": "postgresql.cnpg.io/v1",
        "kind": "ScheduledBackup",
        "metadata": {
            "name": scheduled_backup_name,
            "namespace": "cnpg-system",
        },
        "spec": {
            "schedule": config.schedule,
            "backupOwnerReference": "self",
            "cluster": {"name": f"haven-{tenant.slug}"},
            "method": "barmanObjectStore",
        },
    }

    try:
        # Try patch first, then create
        await asyncio.to_thread(
            k8s.custom_objects.patch_namespaced_custom_object,
            group="postgresql.cnpg.io",
            version="v1",
            namespace="cnpg-system",
            plural="scheduledbackups",
            name=scheduled_backup_name,
            body=manifest,
        )
    except Exception:  # noqa: BLE001
        try:
            await asyncio.to_thread(
                k8s.custom_objects.create_namespaced_custom_object,
                group="postgresql.cnpg.io",
                version="v1",
                namespace="cnpg-system",
                plural="scheduledbackups",
                body=manifest,
            )
        except Exception as exc2:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Failed to configure schedule: {exc2}") from exc2

    return {
        "message": "Backup schedule configured",
        "schedule": config.schedule,
        "retention_days": config.retention_days,
        "tenant": tenant.slug,
    }
