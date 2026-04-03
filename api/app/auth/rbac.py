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
