"""Schemas for billing/usage endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

PLAN_LIMITS: dict[str, dict[str, float]] = {
    "free": {
        "cpu_hours": 100.0,
        "memory_gb_hours": 200.0,
        "storage_gb_hours": 500.0,
        "build_minutes": 60.0,
        "bandwidth_gb": 10.0,
        "max_apps": 2.0,
    },
    "starter": {
        "cpu_hours": 500.0,
        "memory_gb_hours": 1000.0,
        "storage_gb_hours": 2000.0,
        "build_minutes": 300.0,
        "bandwidth_gb": 50.0,
        "max_apps": 10.0,
    },
    "pro": {
        "cpu_hours": 2000.0,
        "memory_gb_hours": 4000.0,
        "storage_gb_hours": 10000.0,
        "build_minutes": 1000.0,
        "bandwidth_gb": 200.0,
        "max_apps": 50.0,
    },
    "enterprise": {
        "cpu_hours": -1.0,  # -1 = unlimited
        "memory_gb_hours": -1.0,
        "storage_gb_hours": -1.0,
        "build_minutes": -1.0,
        "bandwidth_gb": -1.0,
        "max_apps": -1.0,
    },
}

VALID_TIERS = list(PLAN_LIMITS.keys())


class PlanLimits(BaseModel):
    cpu_hours: float
    memory_gb_hours: float
    storage_gb_hours: float
    build_minutes: float
    bandwidth_gb: float
    max_apps: float


# ---------------------------------------------------------------------------
# UsageRecord
# ---------------------------------------------------------------------------


class UsageRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    period_start: datetime
    period_end: datetime | None
    cpu_hours: float
    memory_gb_hours: float
    storage_gb_hours: float
    build_minutes: float
    bandwidth_gb: float
    created_at: datetime
    updated_at: datetime


class UsageSummary(BaseModel):
    tier: str
    limits: PlanLimits
    current_period: UsageRecordResponse | None
    # Percentage used per metric (0-100, or >100 if over quota). None if unlimited.
    usage_pct: dict[str, float | None]
    history: list[UsageRecordResponse]
