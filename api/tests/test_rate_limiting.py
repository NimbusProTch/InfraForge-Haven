"""Tests for Sprint 4: Per-endpoint rate limiting configuration."""

from app.rate_limit import (
    RATE_AUTH,
    RATE_BUILD,
    RATE_SERVICE_PROVISION,
    RATE_TENANT_CREATE,
    RATE_WEBHOOK,
    limiter,
)


def test_limiter_exists():
    """Rate limiter is configured."""
    assert limiter is not None
    assert limiter._default_limits is not None


def test_rate_constants_format():
    """Rate limit constants follow slowapi format (N/period)."""
    for rate in [RATE_AUTH, RATE_BUILD, RATE_SERVICE_PROVISION, RATE_WEBHOOK, RATE_TENANT_CREATE]:
        assert "/" in rate, f"Rate limit '{rate}' must contain '/'"
        count, period = rate.split("/")
        assert count.isdigit(), f"Rate limit count '{count}' must be numeric"
        assert period in ("second", "minute", "hour", "day"), f"Invalid period '{period}'"


def test_build_rate_is_strict():
    """Build rate (10/min) is stricter than global default (200/min)."""
    build_count = int(RATE_BUILD.split("/")[0])
    assert build_count <= 10


def test_service_rate_is_strict():
    """Service provision rate (5/min) is the strictest."""
    svc_count = int(RATE_SERVICE_PROVISION.split("/")[0])
    assert svc_count <= 5


def test_tenant_create_rate():
    """Tenant creation is heavily rate limited."""
    count = int(RATE_TENANT_CREATE.split("/")[0])
    assert count <= 5


def test_webhook_rate_is_generous():
    """Webhooks need higher rate for burst pushes."""
    wh_count = int(RATE_WEBHOOK.split("/")[0])
    assert wh_count >= 30


def test_limiter_imported_in_deployments():
    """deployments.py imports limiter for build endpoint."""
    from app.routers import deployments

    # Check that the module has limiter imported
    assert hasattr(deployments, "limiter")


def test_limiter_imported_in_services():
    """services.py imports limiter for provision endpoint."""
    from app.routers import services

    assert hasattr(services, "limiter")


def test_limiter_imported_in_tenants():
    """tenants.py imports limiter for create endpoint."""
    from app.routers import tenants

    assert hasattr(tenants, "limiter")


def test_limiter_imported_in_webhooks():
    """webhooks.py imports limiter for webhook endpoints."""
    from app.routers import webhooks

    assert hasattr(webhooks, "limiter")
