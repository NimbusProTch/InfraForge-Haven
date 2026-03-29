"""Tests for billing/usage service and endpoints."""

import uuid
from datetime import UTC, datetime

import pytest

from app.models.tenant import Tenant
from app.models.usage_record import UsageRecord
from app.schemas.billing import PLAN_LIMITS
from app.services.usage_service import (
    add_build_minutes,
    compute_usage_pct,
    enforce_build_quota,
    get_or_create_current_record,
    get_plan_limits,
    get_usage_history,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def free_tenant(db_session):
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="free-tenant",
        name="Free Tenant",
        namespace="tenant-free-tenant",
        keycloak_realm="free-tenant",
        tier="free",
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def starter_tenant(db_session):
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="starter-tenant",
        name="Starter Tenant",
        namespace="tenant-starter-tenant",
        keycloak_realm="starter-tenant",
        tier="starter",
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# Plan limits unit tests
# ---------------------------------------------------------------------------


def test_plan_limits_free():
    limits = get_plan_limits("free")
    assert limits.cpu_hours == PLAN_LIMITS["free"]["cpu_hours"]
    assert limits.max_apps == 2.0


def test_plan_limits_enterprise_unlimited():
    limits = get_plan_limits("enterprise")
    assert limits.cpu_hours == -1.0
    assert limits.build_minutes == -1.0


def test_plan_limits_unknown_tier_defaults_to_free():
    limits = get_plan_limits("nonexistent")
    assert limits.max_apps == PLAN_LIMITS["free"]["max_apps"]


# ---------------------------------------------------------------------------
# Usage record service tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_current_record_creates_new(db_session, free_tenant):
    record = await get_or_create_current_record(db_session, free_tenant.id)
    await db_session.commit()

    assert record.tenant_id == free_tenant.id
    assert record.period_end is None
    now = datetime.now(UTC)
    assert record.period_start.year == now.year
    assert record.period_start.month == now.month


@pytest.mark.asyncio
async def test_get_or_create_current_record_reuses_open(db_session, free_tenant):
    r1 = await get_or_create_current_record(db_session, free_tenant.id)
    await db_session.commit()

    r2 = await get_or_create_current_record(db_session, free_tenant.id)
    assert r1.id == r2.id


@pytest.mark.asyncio
async def test_add_build_minutes_accumulates(db_session, free_tenant):
    await add_build_minutes(db_session, free_tenant.id, 10.5)
    await add_build_minutes(db_session, free_tenant.id, 5.0)
    await db_session.commit()

    record = await get_or_create_current_record(db_session, free_tenant.id)
    assert abs(record.build_minutes - 15.5) < 0.001


@pytest.mark.asyncio
async def test_get_usage_history_returns_records(db_session, free_tenant):
    # Create a past record manually
    past = UsageRecord(
        tenant_id=free_tenant.id,
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 2, 1, tzinfo=UTC),
        build_minutes=45.0,
    )
    db_session.add(past)
    await db_session.commit()

    history = await get_usage_history(db_session, free_tenant.id, limit=12)
    assert len(history) >= 1
    assert any(r.build_minutes == 45.0 for r in history)


# ---------------------------------------------------------------------------
# Quota enforcement tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_build_quota_passes_under_limit(db_session, free_tenant):
    """Under the limit → no exception."""
    record = await get_or_create_current_record(db_session, free_tenant.id)
    record.build_minutes = 30.0  # free limit is 60
    await db_session.commit()

    await enforce_build_quota(db_session, free_tenant)  # should not raise


@pytest.mark.asyncio
async def test_enforce_build_quota_raises_at_limit(db_session, free_tenant):
    """At or over the limit → HTTP 402."""
    from fastapi import HTTPException

    record = await get_or_create_current_record(db_session, free_tenant.id)
    record.build_minutes = 60.0  # exactly at free limit
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await enforce_build_quota(db_session, free_tenant)
    assert exc_info.value.status_code == 402


@pytest.mark.asyncio
async def test_enforce_build_quota_enterprise_unlimited(db_session):
    """Enterprise tier never raises regardless of usage."""
    enterprise_tenant = Tenant(
        id=uuid.uuid4(),
        slug="enterprise-co",
        name="Enterprise Co",
        namespace="tenant-enterprise-co",
        keycloak_realm="enterprise-co",
        tier="enterprise",
    )
    db_session.add(enterprise_tenant)
    await db_session.commit()

    record = await get_or_create_current_record(db_session, enterprise_tenant.id)
    record.build_minutes = 99999.0
    await db_session.commit()

    await enforce_build_quota(db_session, enterprise_tenant)  # should not raise


# ---------------------------------------------------------------------------
# Billing endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_endpoint_returns_summary(async_client, free_tenant):
    resp = await async_client.get(f"/api/v1/tenants/{free_tenant.slug}/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert "limits" in data
    assert "current_period" in data
    assert "usage_pct" in data
    assert "history" in data


@pytest.mark.asyncio
async def test_usage_endpoint_tenant_not_found(async_client):
    resp = await async_client.get("/api/v1/tenants/no-such-tenant/usage")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_usage_pct_computed_correctly(async_client, db_session, free_tenant):
    """30 build_minutes on free plan → 50% used."""
    record = await get_or_create_current_record(db_session, free_tenant.id)
    record.build_minutes = 30.0
    await db_session.commit()

    resp = await async_client.get(f"/api/v1/tenants/{free_tenant.slug}/usage")
    assert resp.status_code == 200
    pct = resp.json()["usage_pct"]["build_minutes"]
    assert abs(pct - 50.0) < 0.01


@pytest.mark.asyncio
async def test_update_tier_valid(async_client, free_tenant):
    resp = await async_client.patch(f"/api/v1/tenants/{free_tenant.slug}/tier?tier=starter")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "starter"


@pytest.mark.asyncio
async def test_update_tier_invalid(async_client, free_tenant):
    resp = await async_client.patch(f"/api/v1/tenants/{free_tenant.slug}/tier?tier=diamond")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_compute_usage_pct_none_when_unlimited():
    """Enterprise tier (limit=-1) returns None for all metrics."""
    limits = get_plan_limits("enterprise")
    pct = compute_usage_pct(None, limits)
    # All metrics should be None (unlimited)
    for key in ["cpu_hours", "memory_gb_hours", "storage_gb_hours", "build_minutes", "bandwidth_gb"]:
        assert pct[key] is None
