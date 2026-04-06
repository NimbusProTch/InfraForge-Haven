"""Role-based access control (RBAC) for organization-scoped endpoints.

Usage::

    @router.get("/", dependencies=[Depends(require_org_role("admin", "owner"))])
    async def admin_only(...):
        ...

Or as a function parameter::

    async def my_endpoint(membership: OrganizationMember = Depends(require_org_member)):
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
from app.models.organization import Organization, OrganizationMember, OrgMemberRole

logger = logging.getLogger(__name__)

# Role hierarchy: owner > admin > member > billing
_ORG_ROLE_HIERARCHY = {
    OrgMemberRole.owner: 4,
    OrgMemberRole.admin: 3,
    OrgMemberRole.member: 2,
    OrgMemberRole.billing: 1,
}


async def require_org_member(
    org_slug: str,
    current_user: dict[str, Any] = Depends(verify_token),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> OrganizationMember:
    """Verify the current user is a member of the organization.

    Returns the OrganizationMember record for downstream role checks.
    Raises 403 if the user is not a member.
    """
    user_id = current_user.get("sub", "")
    result = await db.execute(
        select(OrganizationMember)
        .join(Organization, OrganizationMember.organization_id == Organization.id)
        .where(Organization.slug == org_slug, OrganizationMember.user_id == user_id)
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )
    return membership


def require_org_role(*allowed_roles: str) -> Callable:
    """FastAPI dependency factory: require specific role(s) within an organization.

    Usage::

        @router.post("/", dependencies=[Depends(require_org_role("owner", "admin"))])
    """

    async def _check(
        org_slug: str,
        current_user: dict[str, Any] = Depends(verify_token),  # noqa: B008
        db: AsyncSession = Depends(get_db),  # noqa: B008
    ) -> OrganizationMember:
        user_id = current_user.get("sub", "")

        result = await db.execute(
            select(OrganizationMember)
            .join(Organization, OrganizationMember.organization_id == Organization.id)
            .where(Organization.slug == org_slug, OrganizationMember.user_id == user_id)
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this organization",
            )

        if membership.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{membership.role.value}' is not permitted. Required: {', '.join(allowed_roles)}",
            )

        return membership

    return _check
