from collections.abc import AsyncGenerator
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.jwt import verify_token
from app.config import settings
from app.k8s.client import K8sClient, k8s_client
from app.services.argocd_service import ArgoCDService
from app.services.git_queue_service import GitQueueService
from app.services.gitops_service import GitOpsService

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_engine = create_async_engine(settings.database_url, echo=settings.debug, pool_pre_ping=True)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _SessionLocal() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory for use in background tasks."""
    return _SessionLocal


DBSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Kubernetes
# ---------------------------------------------------------------------------
def get_k8s() -> K8sClient:
    return k8s_client


K8sDep = Annotated[K8sClient, Depends(get_k8s)]


# ---------------------------------------------------------------------------
# GitOps
# ---------------------------------------------------------------------------
_gitops_service = GitOpsService()
_argocd_service = ArgoCDService()


def get_gitops() -> GitOpsService:
    return _gitops_service


def get_argocd() -> ArgoCDService:
    return _argocd_service


GitOpsDep = Annotated[GitOpsService, Depends(get_gitops)]
ArgoCDDep = Annotated[ArgoCDService, Depends(get_argocd)]

# ---------------------------------------------------------------------------
# Git Queue (Redis-backed, optional)
# ---------------------------------------------------------------------------
_redis_client: aioredis.Redis | None = None
_git_queue_service: GitQueueService | None = None


def get_git_queue() -> GitQueueService | None:
    """Return a GitQueueService backed by Redis, or None if not configured."""
    if not settings.redis_url:
        return None
    global _redis_client, _git_queue_service  # noqa: PLW0603
    if _git_queue_service is None:
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=False)
        _git_queue_service = GitQueueService(_redis_client)
    return _git_queue_service


GitQueueDep = Annotated[GitQueueService | None, Depends(get_git_queue)]

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
CurrentUser = Annotated[dict[str, Any], Depends(verify_token)]


# ---------------------------------------------------------------------------
# Common tenant lookup helpers (shared across routers)
# ---------------------------------------------------------------------------
#
# H3e (P2.5 / Sprint H3): canonical tenant-resolution helpers. Pre-fix
# every router (~15) carried its own copy of `_get_tenant_or_404`. The
# H0 audit found that 7 of those copies forgot the membership check
# entirely (audit, backup, billing, pvcs, observability, environments,
# cronjobs, domains, canary, gdpr) and 4 were "fail-open" (signature
# `current_user: dict | None = None` would silently accept None).
#
# H0-9 + H0-10 closed all those gaps via inline helpers in each router.
# This module provides the canonical version that Sprint H3 will migrate
# routers to one-by-one. The legacy `get_tenant_or_404` function below
# is kept for backwards compatibility (it's not yet imported anywhere)
# but new code should prefer the FastAPI dependency `require_tenant_member`.


async def _lookup_tenant_with_membership(
    tenant_slug: str,
    db: AsyncSession,
    current_user: dict[str, Any],
) -> Any:
    """Internal: load a Tenant by slug + verify caller is a member.

    Raises:
        HTTPException(404): tenant does not exist
        HTTPException(403): caller is not a member of the tenant

    `current_user` is MANDATORY — there is no fail-open path. A future
    caller that omits the parameter gets a TypeError at call time, not a
    silent cross-tenant leak at request time.
    """
    from fastapi import HTTPException
    from sqlalchemy import select

    from app.models.tenant import Tenant
    from app.models.tenant_member import TenantMember

    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    user_id = current_user.get("sub", "")
    member_q = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant.id,
            TenantMember.user_id == user_id,
        )
    )
    if member_q.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="You are not a member of this tenant")
    return tenant


async def require_tenant_member(
    tenant_slug: str,
    db: DBSession,
    current_user: CurrentUser,
) -> Any:
    """FastAPI dependency: resolve `{tenant_slug}` from the path AND assert
    the caller is a TenantMember of it. Returns the Tenant object.

    Use this as a route-level dependency:

        @router.get("/{tenant_slug}/audit-logs")
        async def list_audit_logs(
            tenant_slug: str,
            db: DBSession,
            current_user: CurrentUser,
            tenant: Tenant = Depends(require_tenant_member),
        ):
            # tenant is guaranteed to exist + caller guaranteed to be a member
            ...

    Or with the type alias:

        async def list_audit_logs(tenant: TenantMembership):
            ...

    Sprint H3 (P2.5) is migrating per-router `_get_tenant_or_404` helpers
    to use this. The migration is gradual — each router PR is its own
    review unit.
    """
    return await _lookup_tenant_with_membership(tenant_slug, db, current_user)


# Type alias for the dependency-injected Tenant.
# Routers can use either `Depends(require_tenant_member)` or
# `tenant: TenantMembership` for cleaner signatures.
from app.models.tenant import Tenant  # noqa: E402

TenantMembership = Annotated[Tenant, Depends(require_tenant_member)]


async def get_tenant_or_404(
    tenant_slug: str,
    db: AsyncSession,
    current_user: dict[str, Any] | None = None,
) -> Any:
    """LEGACY (pre-H0): fetch a tenant by slug or raise 404. If *current_user*
    is provided, also verifies the user is a member of the tenant (403).

    DEPRECATED — use `require_tenant_member` (FastAPI dependency) for new
    code. This function is kept for backwards compatibility but has the
    same fail-open trap that H0-10 removed from per-router copies: if a
    caller forgets to pass `current_user`, the membership check is
    silently skipped. The fix is to migrate to the new dependency.
    """
    if current_user is None:
        # Sprint H3 (P2.5): document the deprecated path. We log a warning
        # so any caller still using this in production becomes visible in
        # the haven-api logs and can be migrated.
        import logging

        logging.getLogger(__name__).warning(
            "deps.get_tenant_or_404 called without current_user — "
            "this is the deprecated fail-open path. Migrate to "
            "deps.require_tenant_member."
        )

    from fastapi import HTTPException
    from sqlalchemy import select

    from app.models.tenant import Tenant as _Tenant

    result = await db.execute(select(_Tenant).where(_Tenant.slug == tenant_slug))
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
