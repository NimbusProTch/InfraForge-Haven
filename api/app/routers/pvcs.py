"""Persistent Volume Claim (PVC) management endpoints.

Sprint 11: PVC CRUD — create Longhorn RWO volumes for tenant applications.
PVCs are created in the tenant's namespace and can be mounted into applications.
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import CurrentUser, DBSession, K8sDep
from app.models.application import Application
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/apps/{app_slug}/volumes", tags=["volumes"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class VolumeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    mount_path: str = Field(..., min_length=1, max_length=255)
    size_gi: int = Field(..., ge=1, le=500, description="Storage size in GiB")
    storage_class: str = Field(default="longhorn", max_length=64)
    access_mode: str = Field(default="ReadWriteOnce", pattern=r"^(ReadWriteOnce|ReadWriteMany|ReadOnlyMany)$")


class VolumeItem(BaseModel):
    name: str
    mount_path: str
    size_gi: int
    storage_class: str
    access_mode: str
    pvc_name: str
    namespace: str
    phase: str | None = None
    capacity: str | None = None


class VolumeListResponse(BaseModel):
    app_slug: str
    k8s_available: bool
    volumes: list[VolumeItem]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_tenant_or_404(tenant_slug: str, db: DBSession, current_user: dict) -> Tenant:
    """H0-9: Lock PVC inventory to tenant members."""
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    t = result.scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    user_id = current_user.get("sub", "")
    member_q = await db.execute(
        select(TenantMember).where(TenantMember.tenant_id == t.id, TenantMember.user_id == user_id)
    )
    if member_q.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="You are not a member of this tenant")
    return t


async def _get_app_or_404(tenant_id: uuid.UUID, app_slug: str, db: DBSession) -> Application:
    result = await db.execute(
        select(Application).where(Application.tenant_id == tenant_id, Application.slug == app_slug)
    )
    a = result.scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return a


def _pvc_name(app_slug: str, volume_name: str) -> str:
    return f"{app_slug}-{volume_name}"[:63]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=VolumeListResponse)
async def list_volumes(
    tenant_slug: str, app_slug: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> VolumeListResponse:
    """List PVCs attached to an application."""
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    if not k8s.is_available():
        return VolumeListResponse(app_slug=app.slug, k8s_available=False, volumes=[])

    volumes: list[VolumeItem] = []
    app_volumes = app.volumes or []

    for vol_spec in app_volumes:
        pvc_name = _pvc_name(app.slug, vol_spec["name"])
        phase = None
        capacity = None

        try:
            pvc = await asyncio.to_thread(
                k8s.core_v1.read_namespaced_persistent_volume_claim,
                name=pvc_name,
                namespace=tenant.namespace,
            )
            phase = pvc.status.phase
            cap = pvc.status.capacity or {}
            capacity = cap.get("storage")
        except Exception:  # noqa: BLE001
            pass

        volumes.append(
            VolumeItem(
                name=vol_spec["name"],
                mount_path=vol_spec["mount_path"],
                size_gi=vol_spec["size_gi"],
                storage_class=vol_spec.get("storage_class", "longhorn"),
                access_mode=vol_spec.get("access_mode", "ReadWriteOnce"),
                pvc_name=pvc_name,
                namespace=tenant.namespace,
                phase=phase,
                capacity=capacity,
            )
        )

    return VolumeListResponse(app_slug=app.slug, k8s_available=True, volumes=volumes)


@router.post("", response_model=VolumeItem, status_code=status.HTTP_201_CREATED)
async def create_volume(
    tenant_slug: str,
    app_slug: str,
    body: VolumeCreate,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> VolumeItem:
    """Create a PVC and attach it to an application.

    The volume spec is persisted in the Application.volumes JSON field.
    A PVC is created in K8s when the cluster is available.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    # Check for duplicate volume name
    existing_volumes = list(app.volumes or [])
    if any(v["name"] == body.name for v in existing_volumes):
        raise HTTPException(status_code=409, detail=f"Volume '{body.name}' already exists")

    pvc_name = _pvc_name(app.slug, body.name)

    # Persist volume spec to Application model
    vol_spec = {
        "name": body.name,
        "mount_path": body.mount_path,
        "size_gi": body.size_gi,
        "storage_class": body.storage_class,
        "access_mode": body.access_mode,
    }
    existing_volumes.append(vol_spec)
    app.volumes = existing_volumes
    await db.commit()
    await db.refresh(app)

    # Create PVC in K8s
    phase = None
    if k8s.is_available():
        pvc_manifest = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": pvc_name,
                "namespace": tenant.namespace,
                "labels": {"app": app.slug, "tenant": tenant.slug, "haven-volume": "true"},
            },
            "spec": {
                "accessModes": [body.access_mode],
                "storageClassName": body.storage_class,
                "resources": {"requests": {"storage": f"{body.size_gi}Gi"}},
            },
        }
        try:
            pvc = await asyncio.to_thread(
                k8s.core_v1.create_namespaced_persistent_volume_claim,
                namespace=tenant.namespace,
                body=pvc_manifest,
            )
            phase = pvc.status.phase
        except Exception as exc:  # noqa: BLE001
            logger.warning("K8s PVC creation failed (DB record kept): %s", exc)

    return VolumeItem(
        name=body.name,
        mount_path=body.mount_path,
        size_gi=body.size_gi,
        storage_class=body.storage_class,
        access_mode=body.access_mode,
        pvc_name=pvc_name,
        namespace=tenant.namespace,
        phase=phase,
    )


@router.delete("/{volume_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_volume(
    tenant_slug: str,
    app_slug: str,
    volume_name: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> None:
    """Delete a PVC and remove it from the application's volume list."""
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    existing_volumes = list(app.volumes or [])
    vol_spec = next((v for v in existing_volumes if v["name"] == volume_name), None)
    if vol_spec is None:
        raise HTTPException(status_code=404, detail=f"Volume '{volume_name}' not found")

    pvc_name = _pvc_name(app.slug, volume_name)

    # Delete from K8s first
    if k8s.is_available():
        try:
            await asyncio.to_thread(
                k8s.core_v1.delete_namespaced_persistent_volume_claim,
                name=pvc_name,
                namespace=tenant.namespace,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("K8s PVC delete failed (continuing DB delete): %s", exc)

    # Remove from application volumes
    app.volumes = [v for v in existing_volumes if v["name"] != volume_name]
    await db.commit()
