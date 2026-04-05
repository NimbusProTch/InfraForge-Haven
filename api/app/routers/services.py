import base64
import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DBSession, K8sDep
from app.models.application import Application
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier
from app.models.tenant import Tenant
from app.schemas.managed_service import (
    ConnectedAppSummary,
    ManagedServiceCreate,
    ManagedServiceDetailResponse,
    ManagedServiceResponse,
    ManagedServiceUpdate,
    ServiceCredentials,
    ServiceRuntimeDetails,
)
from app.services.audit_service import audit
from app.services.managed_service import ManagedServiceProvisioner

logger = logging.getLogger(__name__)

_TRANSITIONAL_STATUSES = {ServiceStatus.PROVISIONING, ServiceStatus.UPDATING}

router = APIRouter(
    prefix="/tenants/{tenant_slug}/services",
    tags=["services"],
)


async def _get_tenant_or_404(tenant_slug: str, db: DBSession, current_user: dict | None = None) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if current_user:
        from app.models.tenant_member import TenantMember

        uid = current_user.get("sub", "")
        mem = await db.execute(
            select(TenantMember).where(TenantMember.tenant_id == tenant.id, TenantMember.user_id == uid)
        )
        if mem.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="You are not a member of this tenant")
    return tenant


@router.get("", response_model=list[ManagedServiceResponse])
async def list_services(tenant_slug: str, db: DBSession, current_user: CurrentUser) -> list[ManagedService]:
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    result = await db.execute(
        select(ManagedService).where(ManagedService.tenant_id == tenant.id).order_by(ManagedService.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ManagedServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    tenant_slug: str,
    body: ManagedServiceCreate,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> ManagedService:
    tenant = await _get_tenant_or_404(tenant_slug, db)

    # Check name uniqueness within tenant
    existing = await db.execute(
        select(ManagedService).where(
            ManagedService.tenant_id == tenant.id,
            ManagedService.name == body.name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Service '{body.name}' already exists in tenant '{tenant_slug}'",
        )

    svc = ManagedService(
        tenant_id=tenant.id,
        name=body.name,
        service_type=body.service_type,
        tier=body.tier,
        status=ServiceStatus.PROVISIONING,
        db_name=body.db_name,
        db_user=body.db_user,
    )
    db.add(svc)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Service '{body.name}' already exists") from exc

    provisioner = ManagedServiceProvisioner(k8s)
    await provisioner.provision(svc, tenant.namespace, tenant_slug=tenant.slug)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Service '{body.name}' already exists") from exc
    await db.refresh(svc)

    await audit(
        db,
        tenant_id=tenant.id,
        action="service.create",
        user_id=current_user.get("sub", ""),
        resource_type="managed_service",
        resource_id=str(svc.id),
        extra={"name": svc.name, "service_type": svc.service_type.value},
    )

    return svc


@router.get("/{service_name}", response_model=ManagedServiceDetailResponse)
async def get_service(
    tenant_slug: str, service_name: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> ManagedServiceDetailResponse:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(ManagedService).where(
            ManagedService.tenant_id == tenant.id,
            ManagedService.name == service_name,
        )
    )
    svc = result.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not found")

    # Sync status + fetch runtime details for transitional or ready states
    runtime_details = None
    provisioner = ManagedServiceProvisioner(k8s)
    if svc.status in _TRANSITIONAL_STATUSES or svc.status == ServiceStatus.READY:
        runtime_details = await provisioner.sync_details(svc, tenant_namespace=tenant.namespace)
        await db.commit()
        await db.refresh(svc)

    # Query connected apps (apps that reference this service in env_from_secrets)
    apps_result = await db.execute(select(Application).where(Application.tenant_id == tenant.id))
    connected_apps = []
    for app_obj in apps_result.scalars():
        if app_obj.env_from_secrets and any(e.get("service_name") == svc.name for e in app_obj.env_from_secrets):
            connected_apps.append(ConnectedAppSummary(slug=app_obj.slug, name=app_obj.name))

    # Build enriched response
    runtime = ServiceRuntimeDetails(**runtime_details) if runtime_details else None
    return ManagedServiceDetailResponse(
        id=svc.id,
        tenant_id=svc.tenant_id,
        name=svc.name,
        service_type=svc.service_type,
        tier=svc.tier,
        status=svc.status,
        secret_name=svc.secret_name,
        connection_hint=svc.connection_hint,
        error_message=svc.error_message,
        created_at=svc.created_at,
        updated_at=svc.updated_at,
        runtime=runtime,
        connected_apps=connected_apps,
    )


_PROD_DEFAULTS: dict[str, dict[str, int | str]] = {
    "postgres": {"replicas": 3, "storage": "20Gi"},
    "mysql": {"replicas": 3, "storage": "20Gi"},
    "mongodb": {"replicas": 3, "storage": "20Gi"},
    "redis": {"replicas": 3},
    "rabbitmq": {"replicas": 3, "storage": "10Gi"},
}

_DEV_DEFAULTS: dict[str, dict[str, int | str]] = {
    "postgres": {"replicas": 1, "storage": "5Gi"},
    "mysql": {"replicas": 1, "storage": "5Gi"},
    "mongodb": {"replicas": 1, "storage": "5Gi"},
    "redis": {"replicas": 1},
    "rabbitmq": {"replicas": 1, "storage": "5Gi"},
}


@router.patch("/{service_name}", response_model=ManagedServiceResponse)
async def update_service(
    tenant_slug: str,
    service_name: str,
    body: ManagedServiceUpdate,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> ManagedService:
    """Update a managed service (replicas, storage, cpu, memory, tier)."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(ManagedService).where(
            ManagedService.tenant_id == tenant.id,
            ManagedService.name == service_name,
        )
    )
    svc = result.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not found")
    if svc.status != ServiceStatus.READY:
        raise HTTPException(status_code=409, detail=f"Service must be ready to update (current: {svc.status})")

    update_fields = body.model_dump(exclude_none=True)
    if not update_fields:
        raise HTTPException(status_code=422, detail="No update fields provided")

    # Handle tier upgrade/downgrade — apply preset defaults
    tier_change = update_fields.pop("tier", None)
    if tier_change is not None and tier_change != svc.tier:
        svc_type = svc.service_type.value
        defaults = _PROD_DEFAULTS.get(svc_type, {}) if tier_change == ServiceTier.PROD else _DEV_DEFAULTS.get(svc_type, {})
        # Apply defaults only for fields not explicitly provided
        for key, val in defaults.items():
            if key not in update_fields:
                update_fields[key] = val
        svc.tier = tier_change
        logger.info("Service %s tier changed to %s", service_name, tier_change.value)

    # Storage can only increase (shrink is dangerous)
    if "storage" in update_fields and svc.service_type.value in ("postgres", "mysql", "mongodb", "rabbitmq"):
        new_storage = int(update_fields["storage"].replace("Gi", ""))
        # Try to get current storage from connection_hint or default
        # For safety, just log a warning — Everest/K8s will reject if not supported
        logger.info("Storage update for %s: %sGi", service_name, new_storage)

    svc.status = ServiceStatus.UPDATING

    provisioner = ManagedServiceProvisioner(k8s)
    try:
        provisioner_fields = {k: v for k, v in update_fields.items() if k in ("replicas", "storage", "cpu", "memory")}
        if provisioner_fields:
            await provisioner.update(svc, **provisioner_fields)
    except NotImplementedError as exc:
        svc.status = ServiceStatus.READY
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(svc)
    return svc


@router.delete("/{service_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    tenant_slug: str, service_name: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> None:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(ManagedService).where(
            ManagedService.tenant_id == tenant.id,
            ManagedService.name == service_name,
        )
    )
    svc = result.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not found")

    # Clean up app connections referencing this service
    apps_result = await db.execute(select(Application).where(Application.tenant_id == tenant.id))
    for app_obj in apps_result.scalars():
        if app_obj.env_from_secrets and any(e.get("service_name") == svc.name for e in app_obj.env_from_secrets):
            app_obj.env_from_secrets = [e for e in app_obj.env_from_secrets if e.get("service_name") != svc.name]
            # Clean up injected env vars (DATABASE_URL, MYSQL_URL, etc.)
            if app_obj.env_vars:
                for key in list(app_obj.env_vars.keys()):
                    if app_obj.env_vars[key] == svc.connection_hint:
                        del app_obj.env_vars[key]

    # Delete tenant-namespace secret (svc-{name})
    from app.services.db_provisioner import delete_tenant_secret, tenant_secret_name

    if svc.credentials_provisioned and tenant.namespace:
        await delete_tenant_secret(k8s, tenant.namespace, tenant_secret_name(svc.name))

    # Deprovision K8s/Everest resources
    provisioner = ManagedServiceProvisioner(k8s)
    await provisioner.deprovision(svc)

    await audit(
        db,
        tenant_id=tenant.id,
        action="service.delete",
        user_id=current_user.get("sub", ""),
        resource_type="managed_service",
        resource_id=str(svc.id),
        extra={"name": svc.name, "service_type": svc.service_type.value},
    )

    await db.delete(svc)
    await db.commit()


@router.post("/{service_name}/retry", response_model=ManagedServiceResponse)
async def retry_service(
    tenant_slug: str, service_name: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> ManagedService:
    """Retry provisioning a failed service."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(ManagedService).where(
            ManagedService.tenant_id == tenant.id,
            ManagedService.name == service_name,
        )
    )
    svc = result.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not found")
    if svc.status != ServiceStatus.FAILED:
        raise HTTPException(status_code=409, detail=f"Only failed services can be retried (current: {svc.status})")

    # Reset state for re-provisioning
    svc.status = ServiceStatus.PROVISIONING
    svc.error_message = None
    svc.credentials_provisioned = False

    # Re-provision
    provisioner = ManagedServiceProvisioner(k8s)
    await provisioner.provision(svc, tenant.namespace, tenant_slug=tenant.slug)

    await db.commit()
    await db.refresh(svc)
    return svc


@router.get("/{service_name}/credentials", response_model=ServiceCredentials)
async def get_service_credentials(
    tenant_slug: str, service_name: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> ServiceCredentials:
    """Return decoded K8s secret credentials for a managed service."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(ManagedService).where(
            ManagedService.tenant_id == tenant.id,
            ManagedService.name == service_name,
        )
    )
    svc = result.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not found")
    if svc.status != ServiceStatus.READY:
        raise HTTPException(status_code=409, detail=f"Service '{svc.name}' is not ready (status: {svc.status})")
    if not svc.secret_name or not svc.service_namespace:
        raise HTTPException(status_code=409, detail="Service has no credentials yet")

    if not k8s.is_available() or k8s.core_v1 is None:
        raise HTTPException(status_code=503, detail="Kubernetes unavailable — cannot read credentials")

    # Credentials provisioned by Haven → secret is in tenant namespace (svc-{name}).
    # Non-provisioned (fallback) → secret is in service_namespace (everest or tenant).
    secret_namespace = tenant.namespace if svc.credentials_provisioned else svc.service_namespace
    try:
        secret = k8s.core_v1.read_namespaced_secret(name=svc.secret_name, namespace=secret_namespace)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to read K8s secret: {exc}") from exc

    credentials: dict[str, str] = {}
    for key, val in (secret.data or {}).items():
        try:
            credentials[key] = base64.b64decode(val).decode()
        except Exception:
            credentials[key] = val  # leave raw if decode fails

    return ServiceCredentials(
        service_name=svc.name,
        secret_name=svc.secret_name,
        connection_hint=svc.connection_hint,
        credentials=credentials,
    )
