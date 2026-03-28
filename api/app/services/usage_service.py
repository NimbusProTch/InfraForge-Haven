"""Usage service — collect K8s metrics and enforce plan quotas."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select

from app.models.usage_record import UsageRecord

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.k8s.client import K8sClient
    from app.models.tenant import Tenant
from app.schemas.billing import PLAN_LIMITS, PlanLimits

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Current period helpers
# ---------------------------------------------------------------------------


def _period_start_for(ts: datetime) -> datetime:
    """Return the first second of the calendar month containing *ts* (UTC)."""
    return datetime(ts.year, ts.month, 1, tzinfo=UTC)


async def get_or_create_current_record(db: AsyncSession, tenant_id: uuid.UUID) -> UsageRecord:
    """Return the open UsageRecord for this month, creating it if absent."""
    now = datetime.now(UTC)
    start = _period_start_for(now)

    result = await db.execute(
        select(UsageRecord)
        .where(UsageRecord.tenant_id == tenant_id)
        .where(UsageRecord.period_end.is_(None))
        .order_by(UsageRecord.period_start.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()

    # Re-use if the open record is for the current month
    if record and record.period_start.year == start.year and record.period_start.month == start.month:
        return record

    # Close the previous open record (if any) and open a new one
    if record and record.period_end is None:
        record.period_end = start
        await db.flush()

    new_record = UsageRecord(tenant_id=tenant_id, period_start=start)
    db.add(new_record)
    await db.flush()
    return new_record


# ---------------------------------------------------------------------------
# Usage accumulation (called from background task or build pipeline)
# ---------------------------------------------------------------------------


async def add_build_minutes(db: AsyncSession, tenant_id: uuid.UUID, minutes: float) -> None:
    """Increment build_minutes on the current open usage record."""
    record = await get_or_create_current_record(db, tenant_id)
    record.build_minutes += minutes
    await db.flush()


async def collect_k8s_usage(db: AsyncSession, k8s: K8sClient, tenant: Tenant) -> None:
    """Sample current CPU/memory from the metrics-server and accumulate to usage.

    This is designed to be called every N minutes by a background task.
    It converts instantaneous metrics into approximate hour-fractions.
    """
    if not k8s.is_available():
        return

    record = await get_or_create_current_record(db, tenant.id)

    try:
        metrics = k8s.custom_objects.list_namespaced_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            namespace=tenant.namespace,
            plural="pods",
        )
    except Exception as exc:
        logger.debug("Metrics unavailable for tenant %s: %s", tenant.slug, exc)
        return

    total_cpu_millicores = 0
    total_memory_mi = 0

    for pod in metrics.get("items", []):
        for container in pod.get("containers", []):
            usage = container.get("usage", {})
            cpu_raw = usage.get("cpu", "0m")
            mem_raw = usage.get("memory", "0Mi")

            # Parse millicores: "42m" → 42, "1" → 1000
            if cpu_raw.endswith("m"):
                total_cpu_millicores += int(cpu_raw[:-1])
            else:
                total_cpu_millicores += int(float(cpu_raw)) * 1000

            # Parse MiB: "128Mi" → 128, "1Gi" → 1024
            if mem_raw.endswith("Ki"):
                total_memory_mi += int(mem_raw[:-2]) / 1024
            elif mem_raw.endswith("Mi"):
                total_memory_mi += int(mem_raw[:-2])
            elif mem_raw.endswith("Gi"):
                total_memory_mi += int(mem_raw[:-2]) * 1024

    # Assume this function is called every 5 minutes → 5/60 of an hour
    fraction = 5 / 60
    record.cpu_hours += (total_cpu_millicores / 1000) * fraction
    record.memory_gb_hours += (total_memory_mi / 1024) * fraction
    await db.flush()


# ---------------------------------------------------------------------------
# History query
# ---------------------------------------------------------------------------


async def get_usage_history(
    db: AsyncSession, tenant_id: uuid.UUID, limit: int = 12
) -> list[UsageRecord]:
    """Return up to *limit* most recent closed + open records (newest first)."""
    result = await db.execute(
        select(UsageRecord)
        .where(UsageRecord.tenant_id == tenant_id)
        .order_by(UsageRecord.period_start.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Plan limits helpers
# ---------------------------------------------------------------------------


def get_plan_limits(tier: str) -> PlanLimits:
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    return PlanLimits(**limits)


def compute_usage_pct(record: UsageRecord | None, limits: PlanLimits) -> dict[str, float | None]:
    """Return percentage used per metric. None = unlimited."""
    if record is None:
        return {k: 0.0 if getattr(limits, k) >= 0 else None for k in PlanLimits.model_fields}

    def _pct(used: float, limit: float) -> float | None:
        if limit < 0:
            return None
        if limit == 0:
            return 100.0 if used > 0 else 0.0
        return round(used / limit * 100, 2)

    return {
        "cpu_hours": _pct(record.cpu_hours, limits.cpu_hours),
        "memory_gb_hours": _pct(record.memory_gb_hours, limits.memory_gb_hours),
        "storage_gb_hours": _pct(record.storage_gb_hours, limits.storage_gb_hours),
        "build_minutes": _pct(record.build_minutes, limits.build_minutes),
        "bandwidth_gb": _pct(record.bandwidth_gb, limits.bandwidth_gb),
        "max_apps": None,  # checked separately
    }


# ---------------------------------------------------------------------------
# Quota enforcement
# ---------------------------------------------------------------------------


async def enforce_app_quota(db: AsyncSession, tenant: Tenant) -> None:
    """Raise HTTP 402 if tenant has reached the max_apps limit for their tier."""
    limits = get_plan_limits(tenant.tier)
    max_apps = limits.max_apps
    if max_apps < 0:
        return  # unlimited

    # Count active apps
    from sqlalchemy import func as sqlfunc

    from app.models.application import Application

    result = await db.execute(
        select(sqlfunc.count(Application.id)).where(Application.tenant_id == tenant.id)
    )
    current_count = result.scalar_one()

    if current_count >= int(max_apps):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"App limit reached for '{tenant.tier}' plan ({int(max_apps)} apps). "
                "Upgrade your plan to create more apps."
            ),
        )


async def enforce_build_quota(db: AsyncSession, tenant: Tenant) -> None:
    """Raise HTTP 402 if tenant has exceeded build_minutes quota for the current period."""
    limits = get_plan_limits(tenant.tier)
    if limits.build_minutes < 0:
        return  # unlimited

    record = await get_or_create_current_record(db, tenant.id)
    if record.build_minutes >= limits.build_minutes:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Build minutes exhausted for '{tenant.tier}' plan "
                f"({int(limits.build_minutes)} min/month). Upgrade your plan."
            ),
        )
