"""Backup and Disaster Recovery endpoints.

Provides per-service backup operations:
- On-demand backup trigger
- Backup listing
- Restore from backup
- Scheduled backup configuration (CNPG only)
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import CurrentUser, DBSession, K8sDep
from app.models.managed_service import ManagedService
from app.models.managed_service import ServiceType as ModelServiceType
from app.models.tenant import Tenant
from app.services.backup_service import BackupService, RestoreRequest
from app.services.backup_service import ServiceType as BackupServiceType

logger = logging.getLogger(__name__)

router = APIRouter(tags=["backup"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SERVICE_TYPE_MAP = {
    ModelServiceType.POSTGRES: BackupServiceType.POSTGRES,
    ModelServiceType.MYSQL: BackupServiceType.MYSQL,
    ModelServiceType.MONGODB: BackupServiceType.MONGODB,
}


class BackupStatusItem(BaseModel):
    backup_id: str
    service_name: str
    service_type: str
    phase: str
    started_at: str | None
    finished_at: str | None
    size: str | None
    s3_path: str | None


class BackupListResponse(BaseModel):
    tenant_slug: str
    service_name: str
    k8s_available: bool
    backups: list[BackupStatusItem]


class BackupTriggerResponse(BaseModel):
    message: str
    backup_name: str
    triggered_at: str


class RestoreRequestBody(BaseModel):
    target_time: str | None = None  # ISO 8601 for PITR (PG only)


class RestoreResponse(BaseModel):
    message: str
    restore_name: str
    triggered_at: str


class BackupScheduleConfig(BaseModel):
    schedule: str = "0 2 * * *"  # Default: 2am daily
    retention_days: int = 30
    storage_location: str = "minio"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


async def _get_service_or_404(tenant_slug: str, service_name: str, db: DBSession) -> ManagedService:
    result = await db.execute(
        select(ManagedService)
        .join(Tenant, ManagedService.tenant_id == Tenant.id)
        .where(Tenant.slug == tenant_slug, ManagedService.name == service_name)
    )
    svc = result.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not found")
    if svc.service_type not in _SERVICE_TYPE_MAP:
        raise HTTPException(status_code=400, detail=f"Backup not supported for {svc.service_type}")
    return svc


def _everest_name(tenant_slug: str, service_name: str) -> str:
    """Return the Everest/CRD cluster name: {tenant_slug}-{service_name}."""
    return f"{tenant_slug}-{service_name}"


# ---------------------------------------------------------------------------
# Per-service backup endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/tenants/{tenant_slug}/services/{service_name}/backups",
    response_model=BackupListResponse,
)
async def list_service_backups(
    tenant_slug: str,
    service_name: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> BackupListResponse:
    """List backups for a specific managed service."""
    svc = await _get_service_or_404(tenant_slug, service_name, db)
    backup_svc = BackupService(k8s)
    backup_type = _SERVICE_TYPE_MAP[svc.service_type]
    cluster_name = svc.everest_name or _everest_name(tenant_slug, service_name)

    items = await backup_svc.list_backups(tenant_slug, cluster_name, backup_type)

    return BackupListResponse(
        tenant_slug=tenant_slug,
        service_name=service_name,
        k8s_available=k8s.is_available(),
        backups=[
            BackupStatusItem(
                backup_id=b.backup_id,
                service_name=b.service_name,
                service_type=b.service_type.value,
                phase=b.phase,
                started_at=b.started_at,
                finished_at=b.finished_at,
                size=b.size,
                s3_path=b.s3_path,
            )
            for b in items
        ],
    )


@router.post(
    "/tenants/{tenant_slug}/services/{service_name}/backup",
    response_model=BackupTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_service_backup(
    tenant_slug: str,
    service_name: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> BackupTriggerResponse:
    """Trigger an on-demand backup for a specific managed service."""
    svc = await _get_service_or_404(tenant_slug, service_name, db)

    if not k8s.is_available():
        raise HTTPException(status_code=503, detail="Kubernetes cluster not available")

    backup_svc = BackupService(k8s)
    backup_type = _SERVICE_TYPE_MAP[svc.service_type]
    cluster_name = svc.everest_name or _everest_name(tenant_slug, service_name)

    try:
        backup_name = await backup_svc.trigger_backup(tenant_slug, cluster_name, backup_type)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return BackupTriggerResponse(
        message="Backup triggered successfully",
        backup_name=backup_name,
        triggered_at=datetime.now(UTC).isoformat(),
    )


@router.post(
    "/tenants/{tenant_slug}/services/{service_name}/restore/{backup_id}",
    response_model=RestoreResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def restore_service_backup(
    tenant_slug: str,
    service_name: str,
    backup_id: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
    body: RestoreRequestBody | None = None,
) -> RestoreResponse:
    """Restore a managed service from a specific backup."""
    svc = await _get_service_or_404(tenant_slug, service_name, db)

    if not k8s.is_available():
        raise HTTPException(status_code=503, detail="Kubernetes cluster not available")

    backup_svc = BackupService(k8s)
    backup_type = _SERVICE_TYPE_MAP[svc.service_type]
    cluster_name = svc.everest_name or _everest_name(tenant_slug, service_name)

    request = RestoreRequest(
        tenant_slug=tenant_slug,
        service_name=cluster_name,
        service_type=backup_type,
        backup_id=backup_id,
        target_time=body.target_time if body else None,
    )

    try:
        restore_name = await backup_svc.restore_backup(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RestoreResponse(
        message="Restore initiated successfully",
        restore_name=restore_name,
        triggered_at=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Legacy tenant-level backup endpoints (CNPG only, backward compat)
# ---------------------------------------------------------------------------


class LegacyBackupListResponse(BaseModel):
    tenant_slug: str
    k8s_available: bool
    backups: list[BackupStatusItem]


@router.get("/tenants/{tenant_slug}/backup", response_model=LegacyBackupListResponse)
async def list_tenant_backups(
    tenant_slug: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> LegacyBackupListResponse:
    """List CNPG backups for the tenant's platform database (legacy)."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    backup_svc = BackupService(k8s)
    cluster_name = f"haven-{tenant.slug}"

    items = await backup_svc.list_backups(tenant_slug, cluster_name, BackupServiceType.POSTGRES)

    return LegacyBackupListResponse(
        tenant_slug=tenant.slug,
        k8s_available=k8s.is_available(),
        backups=[
            BackupStatusItem(
                backup_id=b.backup_id,
                service_name=b.service_name,
                service_type=b.service_type.value,
                phase=b.phase,
                started_at=b.started_at,
                finished_at=b.finished_at,
                size=b.size,
                s3_path=b.s3_path,
            )
            for b in items
        ],
    )


@router.post(
    "/tenants/{tenant_slug}/backup",
    response_model=BackupTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_tenant_backup(
    tenant_slug: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> BackupTriggerResponse:
    """Trigger an on-demand CNPG backup for the tenant's platform database (legacy)."""
    tenant = await _get_tenant_or_404(tenant_slug, db)

    if not k8s.is_available():
        raise HTTPException(status_code=503, detail="Kubernetes cluster not available")

    backup_svc = BackupService(k8s)
    cluster_name = f"haven-{tenant.slug}"

    try:
        backup_name = await backup_svc.trigger_backup(tenant_slug, cluster_name, BackupServiceType.POSTGRES)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return BackupTriggerResponse(
        message="Backup triggered successfully",
        backup_name=backup_name,
        triggered_at=datetime.now(UTC).isoformat(),
    )


@router.put("/tenants/{tenant_slug}/backup/schedule", status_code=status.HTTP_200_OK)
async def configure_backup_schedule(
    tenant_slug: str,
    config: BackupScheduleConfig,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> dict:
    """Configure the CNPG scheduled backup for a tenant's database cluster."""
    import asyncio

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
