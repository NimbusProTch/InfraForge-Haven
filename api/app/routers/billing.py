"""Billing and usage endpoints.

H3e (P2.5): migrated to canonical `TenantMembership` dependency from
`app/deps.py`. The local `_get_tenant_or_404` helper has been removed —
the FastAPI dependency now fetches the Tenant by slug AND asserts caller
membership in one declaration. See PR #90 (audit.py POC) for the pattern.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.deps import DBSession, TenantMembership
from app.schemas.billing import VALID_TIERS, UsageSummary
from app.services.usage_service import (
    compute_usage_pct,
    get_or_create_current_record,
    get_plan_limits,
    get_usage_history,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["billing"])


@router.get("/{tenant_slug}/usage", response_model=UsageSummary)
async def get_usage(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    db: DBSession,
    tenant: TenantMembership,
    history_months: int = Query(6, ge=1, le=24, description="Number of past months to include"),
) -> UsageSummary:
    """Return current period usage + history for a tenant."""
    try:
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
    except Exception:
        logger.exception("Failed to compute usage for tenant %s — returning empty state", tenant_slug)
        from app.schemas.billing import PlanLimits

        return UsageSummary(
            tier=tenant.tier or "free",
            limits=PlanLimits(
                cpu_hours=0,
                memory_gb_hours=0,
                storage_gb_hours=0,
                build_minutes=0,
                bandwidth_gb=0,
                max_apps=0,
            ),
            current_period=None,
            usage_pct={},
            history=[],
        )


@router.patch("/{tenant_slug}/tier", response_model=dict)
async def update_tier(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    db: DBSession,
    tenant: TenantMembership,
    tier: str = Query(..., description="New tier: free | starter | pro | enterprise"),
) -> dict:
    """Update tenant billing tier (admin action)."""
    if tier not in VALID_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier '{tier}'. Valid options: {VALID_TIERS}",
        )
    tenant.tier = tier
    await db.commit()
    await db.refresh(tenant)
    return {"slug": tenant.slug, "tier": tenant.tier}
