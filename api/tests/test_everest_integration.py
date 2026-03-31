"""Integration test: Backend API → ManagedServiceProvisioner → Everest API.

This test requires:
- Port-forward to Everest: kubectl port-forward -n everest-system svc/everest 18080:8080
- Local PostgreSQL with haven_platform DB

Run with: EVEREST_URL=http://localhost:18080 pytest tests/test_everest_integration.py -v -s
"""

import asyncio
import logging
import os

import pytest

# Skip entire module if EVEREST_URL is not set (so it doesn't fail in CI)
pytestmark = pytest.mark.skipif(
    not os.environ.get("EVEREST_URL"),
    reason="EVEREST_URL not set — skipping Everest integration tests",
)

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_provision_postgres_via_backend(async_client, db_session, sample_tenant):
    """Full flow: POST /tenants/{slug}/services → ManagedServiceProvisioner → Everest API → DB ready."""
    from app.services.everest_client import everest_client

    # Verify Everest is reachable
    assert everest_client.is_configured(), "Everest client not configured"

    # 1. Create PostgreSQL service via Haven API
    response = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/services",
        json={"name": "integ-test-pg", "service_type": "postgres", "tier": "dev"},
    )
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

    data = response.json()
    assert data["name"] == "integ-test-pg"
    assert data["service_type"] == "postgres"
    assert data["status"] == "provisioning"
    assert data["service_namespace"] == "everest"
    assert data["secret_name"] is not None
    assert data["connection_hint"] is not None
    logger.info("Service created: %s (status=%s)", data["name"], data["status"])

    # 2. Poll for ready status (Everest needs time to provision)
    max_wait = 120  # seconds
    poll_interval = 5
    elapsed = 0
    final_status = "provisioning"

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        status_resp = await async_client.get(
            f"/api/v1/tenants/{sample_tenant.slug}/services/integ-test-pg"
        )
        assert status_resp.status_code == 200
        svc_data = status_resp.json()
        final_status = svc_data["status"]
        logger.info("Poll %ds: status=%s", elapsed, final_status)

        if final_status in ("ready", "failed"):
            break

    assert final_status == "ready", f"Expected 'ready', got '{final_status}' after {elapsed}s"
    logger.info("PostgreSQL DB ready via backend → Everest flow!")

    # 3. Cleanup: delete the service
    del_resp = await async_client.delete(
        f"/api/v1/tenants/{sample_tenant.slug}/services/integ-test-pg"
    )
    assert del_resp.status_code == 204
    logger.info("Service deleted successfully")


@pytest.mark.asyncio
async def test_provision_duplicate_name_rejected(async_client, db_session, sample_tenant):
    """Creating two services with the same name returns 409."""
    # Create first
    resp1 = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/services",
        json={"name": "dup-test-pg", "service_type": "postgres", "tier": "dev"},
    )
    assert resp1.status_code == 201

    # Try duplicate
    resp2 = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/services",
        json={"name": "dup-test-pg", "service_type": "postgres", "tier": "dev"},
    )
    assert resp2.status_code == 409

    # Cleanup
    await async_client.delete(
        f"/api/v1/tenants/{sample_tenant.slug}/services/dup-test-pg"
    )


@pytest.mark.asyncio
async def test_get_nonexistent_service_returns_404(async_client, db_session, sample_tenant):
    """GET for a service that doesn't exist returns 404."""
    resp = await async_client.get(
        f"/api/v1/tenants/{sample_tenant.slug}/services/no-such-service"
    )
    assert resp.status_code == 404
