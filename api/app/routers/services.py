from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DBSession, K8sDep
from app.models.managed_service import ManagedService, ServiceStatus
from app.models.tenant import Tenant
from app.schemas.managed_service import ManagedServiceCreate, ManagedServiceResponse
from app.services.managed_service import ManagedServiceProvisioner

router = APIRouter(
    prefix="/tenants/{tenant_slug}/services",
    tags=["services"],
)


async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.get("", response_model=list[ManagedServiceResponse])
async def list_services(tenant_slug: str, db: DBSession) -> list[ManagedService]:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(ManagedService)
        .where(ManagedService.tenant_id == tenant.id)
        .order_by(ManagedService.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ManagedServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    tenant_slug: str,
    body: ManagedServiceCreate,
    db: DBSession,
    k8s: K8sDep,
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
    )
    db.add(svc)
    await db.flush()

    provisioner = ManagedServiceProvisioner(k8s)
    await provisioner.provision(svc, tenant.namespace)

    await db.commit()
    await db.refresh(svc)
    return svc


@router.get("/{service_name}", response_model=ManagedServiceResponse)
async def get_service(tenant_slug: str, service_name: str, db: DBSession) -> ManagedService:
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
    return svc


@router.delete("/{service_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    tenant_slug: str, service_name: str, db: DBSession, k8s: K8sDep
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

    provisioner = ManagedServiceProvisioner(k8s)
    await provisioner.deprovision(svc)

    await db.delete(svc)
    await db.commit()
