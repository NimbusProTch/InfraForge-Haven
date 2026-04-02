import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DBSession, K8sDep
from app.models.managed_service import ManagedService
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
from app.services.gitops_scaffold import gitops_scaffold
from app.services.keycloak_service import keycloak_service
from app.services.managed_service import ManagedServiceProvisioner
from app.services.tenant_service import TenantService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenants"])


async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.get("/me", response_model=list[TenantResponse])
async def my_tenants(db: DBSession, current_user: CurrentUser) -> list[Tenant]:
    """List tenants the current user is a member of.

    Used by UI after login to show "Your Projects" or redirect to onboarding.
    Returns empty list if user has no tenants → UI shows "Create your first project".
    """
    user_id = current_user.get("sub", "")
    result = await db.execute(
        select(Tenant)
        .join(TenantMember, TenantMember.tenant_id == Tenant.id)
        .where(TenantMember.user_id == user_id)
        .order_by(Tenant.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("", response_model=list[TenantResponse])
async def list_tenants(db: DBSession, current_user: CurrentUser) -> list[Tenant]:
    """List all tenants (admin view). For user-specific list, use GET /tenants/me."""
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

    # Provision K8s resources — rollback DB on failure
    svc = TenantService(k8s)
    try:
        await svc.provision(
            slug=body.slug,
            namespace=namespace,
            cpu_limit=body.cpu_limit,
            memory_limit=body.memory_limit,
            storage_limit=body.storage_limit,
            tier=body.tier,
        )
    except Exception as exc:
        await db.rollback()
        logger.exception("K8s provisioning failed for tenant %s — rolling back", body.slug)
        raise HTTPException(status_code=500, detail=f"Tenant provisioning failed: {exc}") from exc

    # Create per-tenant Keycloak realm (non-blocking — log on failure, don't abort)
    try:
        await keycloak_service.create_realm(body.slug)
    except Exception as exc:
        logger.warning("Keycloak realm creation failed for %s: %s", body.slug, exc)

    # GitOps scaffold: create tenant directory in haven-gitops (non-blocking)
    await gitops_scaffold.scaffold_tenant(body.slug)

    # Auto-add creator as tenant owner
    from app.models.tenant_member import MemberRole

    creator_member = TenantMember(
        tenant_id=tenant.id,
        user_id=current_user.get("sub", ""),
        email=current_user.get("email", current_user.get("preferred_username", "")),
        display_name=current_user.get("name", ""),
        role=MemberRole.owner,
    )
    db.add(creator_member)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Tenant '{body.slug}' already exists")
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

    # 1. Deprovision all managed services (Everest DBs, Redis CRDs, RabbitMQ CRDs)
    provisioner = ManagedServiceProvisioner(k8s)
    result = await db.execute(select(ManagedService).where(ManagedService.tenant_id == tenant.id))
    for svc in result.scalars():
        try:
            await provisioner.deprovision(svc)
        except Exception as exc:
            logger.warning("Service deprovision failed for %s/%s: %s", tenant_slug, svc.name, exc)

    # 2. Delete ApplicationSet + K8s namespace + Harbor project
    tenant_svc = TenantService(k8s)
    await tenant_svc.deprovision(tenant.namespace, slug=tenant.slug)

    # 3. Delete per-tenant Keycloak realm
    try:
        await keycloak_service.delete_realm(tenant.slug)
    except Exception as exc:
        logger.warning("Keycloak realm deletion failed for %s: %s", tenant.slug, exc)

    # 4. GitOps scaffold: remove tenant directory from haven-gitops
    await gitops_scaffold.delete_tenant(tenant.slug)

    # 5. DB cascade delete (tenant → apps → services → deployments)
    await db.delete(tenant)
    await db.commit()
