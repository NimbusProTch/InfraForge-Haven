"""Audit service — write-only log of platform actions.

Usage (inside a router):
    from app.services.audit_service import audit

    await audit(
        db,
        tenant_id=tenant.id,
        action="app.create",
        user_id=current_user.get("sub"),
        resource_type="app",
        resource_id=app.slug,
        ip_address=request.client.host if request.client else None,
        extra={"name": app.name},
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

# ---------------------------------------------------------------------------
# Well-known action constants (not an exhaustive enum — log any string)
# ---------------------------------------------------------------------------
APP_CREATE = "app.create"
APP_UPDATE = "app.update"
APP_DELETE = "app.delete"
DEPLOY_TRIGGER = "deploy.trigger"
DEPLOY_ROLLBACK = "deploy.rollback"
TENANT_CREATE = "tenant.create"
TENANT_UPDATE = "tenant.update"
TENANT_DELETE = "tenant.delete"
SERVICE_CREATE = "service.create"
SERVICE_UPDATE = "service.update"
SERVICE_DELETE = "service.delete"
MEMBER_INVITE = "member.invite"
MEMBER_REMOVE = "member.remove"
MEMBER_ROLE_UPDATE = "member.role_update"


async def audit(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: str,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    extra: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Create an AuditLog entry and commit it."""
    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        extra=extra,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.commit()
    return entry
