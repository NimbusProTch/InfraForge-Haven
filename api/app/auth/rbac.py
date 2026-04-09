"""Role-based access control (RBAC) dependencies for tenant-scoped endpoints.

Usage::

    @router.post("/", dependencies=[Depends(require_role("admin"))])
    async def create_something(...):
        ...

Or as a function parameter::

    async def my_endpoint(membership: TenantMember = Depends(require_tenant_member)):
        ...
"""

import logging
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember

logger = logging.getLogger(__name__)

# Role hierarchy: owner > admin > member > viewer
_ROLE_HIERARCHY = {
    MemberRole.owner: 4,
    MemberRole.admin: 3,
    MemberRole.member: 2,
    MemberRole.viewer: 1,
}


async def require_tenant_member(
    tenant_slug: str,
    current_user: dict[str, Any] = Depends(verify_token),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> TenantMember:
    """Verify the current user is a member of the tenant.

    Returns the TenantMember record for downstream role checks.
    Raises 403 if the user is not a member.
    """
    user_id = current_user.get("sub", "")
    result = await db.execute(
        select(TenantMember)
        .join(Tenant, TenantMember.tenant_id == Tenant.id)
        .where(Tenant.slug == tenant_slug, TenantMember.user_id == user_id)
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this tenant",
        )
    return membership


def require_role(*allowed_roles: str) -> Callable:
    """FastAPI dependency factory: require specific role(s) within a tenant.

    Usage::

        @router.post("/", dependencies=[Depends(require_role("owner", "admin"))])

    The dependency reads ``tenant_slug`` from path params and checks
    that the authenticated user has one of the allowed roles.
    """

    async def _check(
        tenant_slug: str,
        current_user: dict[str, Any] = Depends(verify_token),  # noqa: B008
        db: AsyncSession = Depends(get_db),  # noqa: B008
    ) -> TenantMember:
        user_id = current_user.get("sub", "")

        # Look up membership
        result = await db.execute(
            select(TenantMember)
            .join(Tenant, TenantMember.tenant_id == Tenant.id)
            .where(Tenant.slug == tenant_slug, TenantMember.user_id == user_id)
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this tenant",
            )

        if membership.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{membership.role.value}' is not permitted. Required: {', '.join(allowed_roles)}",
            )

        return membership

    return _check


# ---------------------------------------------------------------------------
# Sprint H2 P8 (#22): platform-admin realm-role check
# ---------------------------------------------------------------------------
#
# `require_platform_admin` is a route-level dependency for cross-tenant
# operations that should only be reachable by Haven SRE / operators —
# things like "list all tenants in the system", "audit log search across
# tenants", "deploy a platform-wide hotfix". The H0 audit found
# `GET /tenants` was leaking the entire customer list to any authenticated
# user (fixed in H0-4 by user-scoping it). Once this dependency is in
# place, the operator-only flavor of `GET /tenants` can come back as
# `GET /admin/tenants` with this guard.
#
# The check reads `realm_access.roles` from the JWT (Keycloak's standard
# claim shape for realm-level roles). Pre-fix the haven-realm.json had no
# `platform-admin` role at all — Sprint H2 P8 will add it. Until then,
# this dependency rejects EVERY request because no token can carry the
# role; that's intentionally fail-closed.
#
# To grant: in the Keycloak admin console (or via JSON), assign the
# `platform-admin` realm role to the user account that needs cross-tenant
# access. Then their next-issued token will carry it in
# `realm_access.roles`.

PLATFORM_ADMIN_ROLE = "platform-admin"


async def require_platform_admin(
    current_user: dict[str, Any] = Depends(verify_token),  # noqa: B008
) -> dict[str, Any]:
    """FastAPI dependency: require the JWT to carry the `platform-admin`
    realm role.

    Returns the decoded JWT payload (so handlers can still read `sub`,
    `email`, etc. from the dependency injection result).

    Raises 403 if:
      - the token has no `realm_access.roles` claim at all (rare —
        Keycloak always emits this for authenticated users)
      - the token's realm roles do not include `platform-admin`

    Usage::

        @router.get("/admin/tenants", dependencies=[Depends(require_platform_admin)])
        async def list_all_tenants_admin(...):
            ...
    """
    realm_access = current_user.get("realm_access") or {}
    roles = realm_access.get("roles") or []
    if PLATFORM_ADMIN_ROLE not in roles:
        logger.warning(
            "platform-admin denied: sub=%s roles=%s",
            current_user.get("sub", "?"),
            roles,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This endpoint requires the '{PLATFORM_ADMIN_ROLE}' realm role",
        )
    return current_user
