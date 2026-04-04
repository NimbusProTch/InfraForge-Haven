import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DBSession, K8sDep
from app.models.managed_service import ManagedService
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
from app.services.gitops_scaffold import gitops_scaffold
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


async def _require_tenant_membership(
    tenant: Tenant, current_user: dict, db: DBSession, min_role: str | None = None
) -> TenantMember:
    """Verify user is a member of this tenant. Returns the membership record."""
    user_id = current_user.get("sub", "")
    result = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant.id,
            TenantMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=403, detail="You are not a member of this tenant")
    if min_role:
        hierarchy = {"owner": 4, "admin": 3, "member": 2, "viewer": 1}
        if hierarchy.get(member.role.value, 0) < hierarchy.get(min_role, 0):
            raise HTTPException(status_code=403, detail=f"Requires {min_role} role or higher")
    return member


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

    # Per-tenant Keycloak realm: DISABLED in Sprint 1 (shared "haven" realm used).
    # Tenant isolation is DB-based (TenantMember table + RBAC).
    # Per-tenant realms will be activated in Sprint 5+ for IdP federation (Azure AD, SAML).
    # Code preserved but not called:
    # await keycloak_service.create_realm(body.slug)

    # GitOps scaffold: create tenant directory in haven-gitops (non-blocking)
    await gitops_scaffold.scaffold_tenant(body.slug)

    # Auto-add creator as tenant owner
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
    tenant = await _get_tenant_or_404(tenant_slug, db)
    await _require_tenant_membership(tenant, current_user, db)
    return tenant


@router.patch("/{tenant_slug}", response_model=TenantResponse)
@router.put("/{tenant_slug}", response_model=TenantResponse)
async def update_tenant(tenant_slug: str, body: TenantUpdate, db: DBSession, current_user: CurrentUser) -> Tenant:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    await _require_tenant_membership(tenant, current_user, db, min_role="admin")

    # Only allow safe fields to be updated
    _MUTABLE_FIELDS = {"name", "cpu_limit", "memory_limit", "storage_limit", "tier", "active", "github_token"}
    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        if field in _MUTABLE_FIELDS:
            setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.delete("/{tenant_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(tenant_slug: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser) -> None:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    await _require_tenant_membership(tenant, current_user, db, min_role="owner")

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

    # 3. Per-tenant Keycloak realm deletion: DISABLED (shared realm model)
    # await keycloak_service.delete_realm(tenant.slug)

    # 4. GitOps scaffold: remove tenant directory from haven-gitops
    await gitops_scaffold.delete_tenant(tenant.slug)

    # 5. DB cascade delete (tenant → apps → services → deployments)
    await db.delete(tenant)
    await db.commit()
