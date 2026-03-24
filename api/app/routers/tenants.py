import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DBSession, K8sDep
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantResponse])
async def list_tenants(db: DBSession) -> list[Tenant]:
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreate, db: DBSession, k8s: K8sDep) -> Tenant:
    # Check slug uniqueness
    existing = await db.execute(select(Tenant).where(Tenant.slug == body.slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Tenant '{body.slug}' already exists")

    namespace = f"tenant-{body.slug}"
    tenant = Tenant(
        slug=body.slug,
        name=body.name,
        namespace=namespace,
        keycloak_realm=f"tenant-{body.slug}",
        cpu_limit=body.cpu_limit,
        memory_limit=body.memory_limit,
        storage_limit=body.storage_limit,
    )
    db.add(tenant)
    await db.flush()  # get ID before provisioning

    svc = TenantService(k8s)
    await svc.provision(
        slug=body.slug,
        namespace=namespace,
        cpu_limit=body.cpu_limit,
        memory_limit=body.memory_limit,
        storage_limit=body.storage_limit,
    )

    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: uuid.UUID, db: DBSession) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(tenant_id: uuid.UUID, body: TenantUpdate, db: DBSession) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(tenant_id: uuid.UUID, db: DBSession, k8s: K8sDep) -> None:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    svc = TenantService(k8s)
    await svc.deprovision(tenant.namespace)

    await db.delete(tenant)
    await db.commit()
