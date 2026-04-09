"""Tenant CRUD endpoints.

H3e (P2.5 / P21 batch 5 / final): migrated to canonical `TenantMembership`
dependency from `app/deps.py`. The local `_get_tenant_or_404` helper has
been removed. The role-aware `_require_tenant_membership` helper is KEPT
because routes that need a min_role check (update_tenant=admin,
delete_tenant=owner) still need it. The dep handles the basic membership
check (404/403); `_require_tenant_membership(..., min_role=...)` layers
the role-hierarchy check on top.

This is the FINAL H3e migration. All 14 routers now use TenantMembership.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.rbac import require_role  # noqa: F401 — available for future use
from app.deps import CurrentUser, DBSession, K8sDep, TenantMembership
from app.models.managed_service import ManagedService
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
from app.services.audit_service import audit
from app.services.gitops_scaffold import gitops_scaffold
from app.services.managed_service import ManagedServiceProvisioner
from app.services.tenant_service import TenantService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenants"])


async def _require_min_role(tenant: Tenant, current_user: dict, db: DBSession, min_role: str) -> TenantMember:
    """Verify the caller has at least `min_role` on this tenant.

    Assumes `TenantMembership` dependency already enforced basic membership
    (so a non-member would have been 403'd before reaching this function).
    Returns the TenantMember record so callers can inspect it.

    Role hierarchy (descending power): owner > admin > member > viewer.
    """
    user_id = current_user.get("sub", "")
    result = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant.id,
            TenantMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        # Defensive — TenantMembership dep should have prevented this.
        raise HTTPException(status_code=403, detail="You are not a member of this tenant")
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
    """List tenants the current user is a member of.

    H0-4: Prior to the fix this endpoint returned EVERY tenant in the system
    to any authenticated user, leaking the customer list and enabling tenant
    enumeration. It now behaves identically to GET /tenants/me — scoped to
    the caller's memberships. A separate "platform admin" view (with proper
    role enforcement) can be added in Sprint H2 if needed.
    """
    user_id = current_user.get("sub", "")
    result = await db.execute(
        select(Tenant)
        .join(TenantMember, TenantMember.tenant_id == Tenant.id)
        .where(TenantMember.user_id == user_id)
        .order_by(Tenant.created_at.desc())
    )
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

    # NOTE: Tenant isolation is DB-based (TenantMember table + RBAC), not
    # per-tenant Keycloak realm. The platform uses a single shared "haven"
    # realm. Per-tenant realm support was removed in Sprint H3 (P2.1) along
    # with the dead KeycloakService methods. If IdP federation requires it
    # in a future sprint, see git history at the H3a commit.

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

    await audit(
        db,
        tenant_id=tenant.id,
        action="tenant.create",
        user_id=current_user.get("sub", ""),
        resource_type="tenant",
        resource_id=str(tenant.id),
        extra={"slug": tenant.slug},
    )

    return tenant


@router.get("/{tenant_slug}", response_model=TenantResponse)
async def get_tenant(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    db: DBSession,  # noqa: ARG001 — kept for parity with other routes; TenantMembership uses it
    tenant: TenantMembership,
) -> Tenant:
    return tenant


@router.patch("/{tenant_slug}", response_model=TenantResponse)
@router.put("/{tenant_slug}", response_model=TenantResponse)
async def update_tenant(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    body: TenantUpdate,
    db: DBSession,
    tenant: TenantMembership,
    current_user: CurrentUser,
) -> Tenant:
    await _require_min_role(tenant, current_user, db, min_role="admin")

    # H0-3: github_token is intentionally excluded — it must only be set via
    # the OAuth callback flow (api/app/routers/github.py). Allowing PATCH would
    # let an admin paste an arbitrary GitHub token (potentially someone else's
    # leaked token) and bypass the OAuth handshake.
    _MUTABLE_FIELDS = {"name", "cpu_limit", "memory_limit", "storage_limit", "tier", "active"}
    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        if field in _MUTABLE_FIELDS:
            setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.delete("/{tenant_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_slug: str,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
    current_user: CurrentUser,
) -> None:
    """Delete tenant with best-effort external cleanup.

    Each external cleanup step is wrapped in try/except so a single failure
    (Harbor unreachable, ArgoCD timeout, Gitea hiccup) cannot leave the tenant
    stuck in the DB. The DB delete ALWAYS runs after the cleanup attempts.
    Cleanup failures are logged for ops to inspect later.
    """
    await _require_min_role(tenant, current_user, db, min_role="owner")
    cleanup_errors: list[str] = []

    # 1. Deprovision all managed services (Everest DBs, Redis CRDs, RabbitMQ CRDs)
    # Reuse the provisioner instance for the orphan-sweep below.
    provisioner = ManagedServiceProvisioner(k8s)
    try:
        result = await db.execute(select(ManagedService).where(ManagedService.tenant_id == tenant.id))
        for svc in result.scalars():
            try:
                await provisioner.deprovision(svc)
            except Exception as exc:
                logger.warning("Service deprovision failed for %s/%s: %s", tenant_slug, svc.name, exc)
                cleanup_errors.append(f"service:{svc.name}")
    except Exception as exc:
        logger.error("Service deprovision loop failed for %s: %s", tenant_slug, exc)
        cleanup_errors.append("services")

    # 1b. DEFENSIVE: sweep any orphan Everest DatabaseClusters whose name
    # starts with `{tenant_slug}-`. The 2026-04-09 cluster audit found 7
    # orphan DBs that the normal deprovision loop skipped because their
    # ManagedService rows had been deleted out-of-band. This sweep is the
    # second line of defense — best-effort, never raises.
    # See ManagedServiceProvisioner.cleanup_orphans_by_prefix() docstring.
    try:
        swept = await provisioner.cleanup_orphans_by_prefix(tenant.slug)
        if swept:
            logger.info("Tenant %s deprovision swept %d orphan Everest DB(s): %s", tenant_slug, len(swept), swept)
    except Exception as exc:
        logger.warning("Orphan Everest sweep failed for %s (non-fatal): %s", tenant_slug, exc)
        cleanup_errors.append("orphan_sweep")

    # 2. Delete ApplicationSet + K8s namespace + Harbor project
    try:
        tenant_svc = TenantService(k8s)
        await tenant_svc.deprovision(tenant.namespace, slug=tenant.slug)
    except Exception as exc:
        logger.error("TenantService.deprovision failed for %s: %s", tenant_slug, exc)
        cleanup_errors.append("tenant_service")

    # NOTE: Per-tenant Keycloak realm deletion removed in Sprint H3 (P2.1).
    # Shared "haven" realm — nothing to delete here. See git history at H3a.

    # 3. GitOps scaffold: remove tenant directory from haven-gitops
    try:
        await gitops_scaffold.delete_tenant(tenant.slug)
    except Exception as exc:
        logger.error("gitops_scaffold.delete_tenant failed for %s: %s", tenant_slug, exc)
        cleanup_errors.append("gitops")

    # 5. Audit log before cascade delete
    try:
        await audit(
            db,
            tenant_id=tenant.id,
            action="tenant.delete",
            user_id=current_user.get("sub", ""),
            resource_type="tenant",
            resource_id=str(tenant.id),
            extra={"slug": tenant.slug, "cleanup_errors": cleanup_errors},
        )
    except Exception as exc:
        logger.error("Audit log failed for tenant delete %s: %s", tenant_slug, exc)

    # 6. DB cascade delete (tenant → apps → services → deployments)
    # ALWAYS runs, even if external cleanup partially failed.
    # Stuck DB records are worse than orphaned external resources, which
    # can be cleaned up by the cleanup-orphan-appsets.sh script.
    await db.delete(tenant)
    await db.commit()

    if cleanup_errors:
        logger.warning(
            "Tenant %s deleted from DB with cleanup errors: %s. "
            "Run scripts/cleanup-orphan-appsets.sh and check Harbor/Gitea manually.",
            tenant_slug,
            ", ".join(cleanup_errors),
        )
