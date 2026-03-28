import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DBSession, K8sDep
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
from app.services.keycloak_service import keycloak_service
from app.services.tenant_service import TenantService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenants"])


async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.get("", response_model=list[TenantResponse])
async def list_tenants(db: DBSession, current_user: CurrentUser) -> list[Tenant]:
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreate, db: DBSession, k8s: K8sDep, current_user: CurrentUser) -> Tenant:
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
        tier=body.tier,
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
        tier=body.tier,
    )

    # Create per-tenant Keycloak realm (non-blocking — log on failure, don't abort)
    try:
        await keycloak_service.create_realm(body.slug)
    except Exception as exc:
        logger.warning("Keycloak realm creation failed for %s: %s", body.slug, exc)

    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.get("/{tenant_slug}", response_model=TenantResponse)
async def get_tenant(tenant_slug: str, db: DBSession, current_user: CurrentUser) -> Tenant:
    return await _get_tenant_or_404(tenant_slug, db)


@router.patch("/{tenant_slug}", response_model=TenantResponse)
@router.put("/{tenant_slug}", response_model=TenantResponse)
async def update_tenant(tenant_slug: str, body: TenantUpdate, db: DBSession, current_user: CurrentUser) -> Tenant:
    tenant = await _get_tenant_or_404(tenant_slug, db)

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.delete("/{tenant_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(tenant_slug: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser) -> None:
    tenant = await _get_tenant_or_404(tenant_slug, db)

    svc = TenantService(k8s)
    await svc.deprovision(tenant.namespace)

    # Delete per-tenant Keycloak realm
    try:
        await keycloak_service.delete_realm(tenant.slug)
    except Exception as exc:
        logger.warning("Keycloak realm deletion failed for %s: %s", tenant.slug, exc)

    await db.delete(tenant)
    await db.commit()
