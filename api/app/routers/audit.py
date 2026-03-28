"""Audit log query endpoints."""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DBSession
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.schemas.audit_log import AuditLogListResponse, AuditLogResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["audit"])


async def _get_tenant_or_404(slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.get("/{tenant_slug}/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    tenant_slug: str,
    db: DBSession,
    current_user: CurrentUser,
    action: str | None = Query(None, description="Filter by action (e.g. app.create)"),
    user_id: str | None = Query(None, description="Filter by user_id (Keycloak sub)"),
    resource_type: str | None = Query(None, description="Filter by resource_type"),
    resource_id: str | None = Query(None, description="Filter by resource_id"),
    start_date: Annotated[datetime | None, Query(description="Filter entries on or after this timestamp")] = None,
    end_date: Annotated[datetime | None, Query(description="Filter entries on or before this timestamp")] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> AuditLogListResponse:
    tenant = await _get_tenant_or_404(tenant_slug, db)

    base_q = select(AuditLog).where(AuditLog.tenant_id == tenant.id)

    if action:
        base_q = base_q.where(AuditLog.action == action)
    if user_id:
        base_q = base_q.where(AuditLog.user_id == user_id)
    if resource_type:
        base_q = base_q.where(AuditLog.resource_type == resource_type)
    if resource_id:
        base_q = base_q.where(AuditLog.resource_id == resource_id)
    if start_date:
        base_q = base_q.where(AuditLog.created_at >= start_date)
    if end_date:
        base_q = base_q.where(AuditLog.created_at <= end_date)

    # Count total (before pagination)
    count_q = select(func.count()).select_from(base_q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    # Paginate
    offset = (page - 1) * page_size
    items_q = base_q.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)
    items_result = await db.execute(items_q)
    items = list(items_result.scalars().all())

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
