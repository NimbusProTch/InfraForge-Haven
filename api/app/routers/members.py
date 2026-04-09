"""Tenant membership management endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.auth.rbac import require_role
from app.deps import CurrentUser, DBSession
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.schemas.tenant_member import TenantMemberInvite, TenantMemberResponse, TenantMemberUpdate
from app.services.audit_service import audit
from app.services.keycloak_service import keycloak_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/members", tags=["members"])


async def _get_tenant_or_404(tenant_slug: str, db: DBSession, current_user: dict) -> Tenant:
    """H0-10: current_user is now MANDATORY (was fail-open `dict | None = None`)."""
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    uid = current_user.get("sub", "")
    mem = await db.execute(select(TenantMember).where(TenantMember.tenant_id == tenant.id, TenantMember.user_id == uid))
    if mem.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="You are not a member of this tenant")
    return tenant


async def _get_member_or_404(tenant_id: uuid.UUID, user_id: str, db: DBSession) -> TenantMember:
    result = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.get("", response_model=list[TenantMemberResponse])
async def list_members(tenant_slug: str, db: DBSession, current_user: CurrentUser) -> list[TenantMember]:
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    result = await db.execute(
        select(TenantMember).where(TenantMember.tenant_id == tenant.id).order_by(TenantMember.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "",
    response_model=TenantMemberResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("owner", "admin"))],
)
async def add_member(
    tenant_slug: str, body: TenantMemberInvite, db: DBSession, current_user: CurrentUser
) -> TenantMember:
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)

    # Prevent duplicate membership
    existing = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant.id,
            TenantMember.email == body.email,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"'{body.email}' is already a member of this tenant")

    # Resolve Keycloak user_id if not supplied
    user_id = body.user_id or ""
    if not user_id:
        try:
            user_id = await keycloak_service.create_user(
                tenant_slug=tenant_slug,
                username=body.email.split("@")[0],
                email=body.email,
                password=_generate_temp_password(),
                role=body.role.value,
            )
        except Exception as exc:
            logger.warning(
                "Keycloak user creation failed for %s in tenant %s: %s",
                body.email,
                tenant_slug,
                exc,
            )
            # Store member in DB with empty user_id — will be linked once they log in
            user_id = ""

    member = TenantMember(
        tenant_id=tenant.id,
        user_id=user_id,
        email=body.email,
        display_name=body.display_name,
        role=body.role,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)

    await audit(
        db,
        tenant_id=tenant.id,
        action="member.add",
        user_id=current_user.get("sub", ""),
        resource_type="member",
        resource_id=str(member.id),
        extra={"email": body.email, "role": body.role.value},
    )

    return member


@router.patch(
    "/{user_id}",
    response_model=TenantMemberResponse,
    dependencies=[Depends(require_role("owner", "admin"))],
)
async def update_member_role(
    tenant_slug: str, user_id: str, body: TenantMemberUpdate, db: DBSession, current_user: CurrentUser
) -> TenantMember:
    """H0-13: PATCH was previously a vertical privilege escalation vector.
    Without `require_role("owner","admin")` any tenant member — including a
    viewer — could promote themselves to owner or demote the actual owner.
    The H0-10 fix made membership mandatory but did not enforce role.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    member = await _get_member_or_404(tenant.id, user_id, db)

    # Cannot downgrade the last owner
    if member.role == MemberRole.owner and body.role != MemberRole.owner:
        owners_result = await db.execute(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant.id,
                TenantMember.role == MemberRole.owner,
            )
        )
        if len(list(owners_result.scalars().all())) <= 1:
            raise HTTPException(status_code=409, detail="Tenant must have at least one owner")

    member.role = body.role
    await db.commit()
    await db.refresh(member)
    return member


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("owner", "admin"))],
)
async def remove_member(tenant_slug: str, user_id: str, db: DBSession, current_user: CurrentUser) -> None:
    """H0-13: DELETE was previously a member-nuking vector. Without role
    enforcement any tenant member could remove other members. The "last
    owner" guard at the bottom prevents total wipe but a viewer could
    still remove every admin and (combined with the PATCH bug) take over.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    member = await _get_member_or_404(tenant.id, user_id, db)

    # Cannot remove the last owner
    if member.role == MemberRole.owner:
        owners_result = await db.execute(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant.id,
                TenantMember.role == MemberRole.owner,
            )
        )
        if len(list(owners_result.scalars().all())) <= 1:
            raise HTTPException(status_code=409, detail="Cannot remove the last owner")

    # Capture the removed user's identifier for the revocation entry
    # before we delete the row.
    removed_user_id = member.user_id

    await audit(
        db,
        tenant_id=tenant.id,
        action="member.remove",
        user_id=current_user.get("sub", ""),
        resource_type="member",
        resource_id=str(member.id),
        extra={"removed_user_id": user_id},
    )

    await db.delete(member)

    # Sprint H2 P9 (#24): force the removed user to re-authenticate so
    # their existing JWT (which may still carry the old tenant in its
    # claims) stops working immediately. The next request from that user
    # gets 401 from `verify_token_not_revoked`, the user re-logs in, and
    # the fresh token reflects the updated membership set.
    #
    # We only do this if there's a real Keycloak `sub` to revoke. Members
    # invited but never logged in have `user_id == ""` and don't need it.
    if removed_user_id:
        from app.services.token_revocation_service import revoke_user

        await revoke_user(
            db,
            user_id=removed_user_id,
            reason=f"removed from tenant {tenant.slug} by {current_user.get('sub', 'unknown')}",
        )

    await db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_temp_password() -> str:
    """Generate a random temporary password for new Keycloak users."""
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(16))
