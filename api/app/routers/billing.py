"""Billing and usage endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.deps import CurrentUser, DBSession
from app.models.tenant import Tenant
from app.schemas.billing import VALID_TIERS, UsageSummary
from app.services.usage_service import (
    compute_usage_pct,
    get_or_create_current_record,
    get_plan_limits,
    get_usage_history,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["billing"])


async def _get_tenant_or_404(slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.get("/{tenant_slug}/usage", response_model=UsageSummary)
async def get_usage(
    tenant_slug: str,
    db: DBSession,
    current_user: CurrentUser,
    history_months: int = Query(6, ge=1, le=24, description="Number of past months to include"),
) -> UsageSummary:
    """Return current period usage + history for a tenant."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    limits = get_plan_limits(tenant.tier)

    current = await get_or_create_current_record(db, tenant.id)
    history = await get_usage_history(db, tenant.id, limit=history_months + 1)
    usage_pct = compute_usage_pct(current, limits)

    from app.schemas.billing import UsageRecordResponse

    return UsageSummary(
        tier=tenant.tier,
        limits=limits,
        current_period=UsageRecordResponse.model_validate(current),
        usage_pct=usage_pct,
        history=[UsageRecordResponse.model_validate(r) for r in history],
    )


@router.patch("/{tenant_slug}/tier", response_model=dict)
async def update_tier(
    tenant_slug: str,
    db: DBSession,
    current_user: CurrentUser,
    tier: str = Query(..., description="New tier: free | starter | pro | enterprise"),
) -> dict:
    """Update tenant billing tier (admin action)."""
    if tier not in VALID_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier '{tier}'. Valid options: {VALID_TIERS}",
        )
    tenant = await _get_tenant_or_404(tenant_slug, db)
    tenant.tier = tier
    await db.commit()
    await db.refresh(tenant)
    return {"slug": tenant.slug, "tier": tenant.tier}
