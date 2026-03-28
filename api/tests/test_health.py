"""Smoke tests for the health endpoints."""

import pytest


@pytest.mark.asyncio
async def test_health_ok(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_cluster_returns_status(async_client):
    """Cluster health endpoint always returns a structured response."""
    response = await async_client.get("/health/cluster")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ("ok", "degraded")
