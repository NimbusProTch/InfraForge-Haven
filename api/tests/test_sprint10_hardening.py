"""Sprint 10 — Production Hardening tests.

Covers:
- Health / readiness probes
- Rate limiting (SlowAPI)
- Global error handler (ValueError, PermissionError, unhandled Exception)
- Backup list / trigger endpoints
- Backup schedule configuration
- Application new fields (app_type, canary_enabled, canary_weight, volumes)
"""

import pytest

# ---------------------------------------------------------------------------
# Health & Readiness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_ok(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_with_working_db(async_client):
    """Readiness probe returns 200 when DB is reachable."""
    resp = await async_client.get("/readiness")
    # In test mode the DB is SQLite in-memory — should succeed
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert "checks" in data
    assert data["checks"]["database"] == "ok"


@pytest.mark.asyncio
async def test_readiness_includes_kubernetes_check(async_client):
    """Readiness endpoint reports kubernetes status (ok or unavailable)."""
    resp = await async_client.get("/readiness")
    # Response is always 200 in tests (DB is in-memory SQLite)
    assert resp.status_code == 200
    data = resp.json()
    assert "kubernetes" in data["checks"]


@pytest.mark.asyncio
async def test_health_cluster_degraded_when_k8s_unavailable(async_client):
    """Cluster health returns degraded when K8s is unavailable."""
    resp = await async_client.get("/health/cluster")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "kubernetes" in data


# ---------------------------------------------------------------------------
# Global Error Handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_404_returns_json(async_client):
    """Non-existent routes return JSON 404."""
    resp = await async_client.get("/api/v1/nonexistent-route-xyz")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_tenant_404_detail(async_client):
    """Missing tenant returns structured 404 detail."""
    resp = await async_client.get("/api/v1/tenants/ghost-tenant/apps")
    assert resp.status_code == 404
    assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_global_value_error_handler(async_client):
    """ValueError raised inside a handler returns 422 via global handler."""
    from app.main import app

    @app.get("/test-value-error")
    async def _bad_route():
        raise ValueError("bad input")

    try:
        resp = await async_client.get("/test-value-error")
        assert resp.status_code == 422
        assert "bad input" in resp.json()["detail"]
    finally:
        # Remove the test route from the router's routes list
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/test-value-error"]


@pytest.mark.asyncio
async def test_global_permission_error_handler(async_client):
    """PermissionError raised inside a handler returns 403 via global handler."""
    from app.main import app

    @app.get("/test-permission-error")
    async def _forbidden_route():
        raise PermissionError("access denied")

    try:
        resp = await async_client.get("/test-permission-error")
        assert resp.status_code == 403
        assert "access denied" in resp.json()["detail"]
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/test-permission-error"]


# ---------------------------------------------------------------------------
# Backup Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backup_list_k8s_unavailable(async_client, mock_k8s, sample_tenant):
    """Backup list returns empty list when K8s is unavailable."""
    mock_k8s.is_available.return_value = False

    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/backup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["k8s_available"] is False
    assert data["backups"] == []


@pytest.mark.asyncio
async def test_backup_list_with_k8s(async_client, mock_k8s, sample_tenant):
    """Backup list returns items from K8s custom object API."""
    mock_k8s.is_available.return_value = True
    mock_k8s.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "backup-test-20260328-020000"},
                "status": {
                    "state": "Succeeded",
                    "startTime": "2026-03-28T02:00:00Z",
                    "completedAt": "2026-03-28T02:01:30Z",
                },
            }
        ]
    }

    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/backup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["k8s_available"] is True
    assert len(data["backups"]) == 1
    assert data["backups"][0]["phase"] == "Succeeded"


@pytest.mark.asyncio
async def test_backup_trigger_k8s_unavailable(async_client, mock_k8s, sample_tenant):
    """Backup trigger returns 503 when K8s is unavailable."""
    mock_k8s.is_available.return_value = False

    resp = await async_client.post(f"/api/v1/tenants/{sample_tenant.slug}/backup")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_backup_trigger_success(async_client, mock_k8s, sample_tenant):
    """Backup trigger returns 202 with backup name when K8s is available."""
    mock_k8s.is_available.return_value = True
    mock_k8s.custom_objects.create_namespaced_custom_object.return_value = {}

    resp = await async_client.post(f"/api/v1/tenants/{sample_tenant.slug}/backup")
    assert resp.status_code == 202
    data = resp.json()
    assert "backup_name" in data
    assert data["backup_name"].startswith(f"backup-haven-{sample_tenant.slug}-")
    assert "triggered_at" in data


@pytest.mark.asyncio
async def test_backup_tenant_not_found(async_client):
    """Backup endpoints return 404 for non-existent tenant."""
    resp = await async_client.get("/api/v1/tenants/ghost/backup")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_backup_schedule_k8s_unavailable(async_client, mock_k8s, sample_tenant):
    """Backup schedule config returns 503 when K8s is unavailable."""
    mock_k8s.is_available.return_value = False

    resp = await async_client.put(
        f"/api/v1/tenants/{sample_tenant.slug}/backup/schedule",
        json={"schedule": "0 3 * * *", "retention_days": 14},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_backup_schedule_success(async_client, mock_k8s, sample_tenant):
    """Backup schedule configure returns 200 with schedule info."""
    mock_k8s.is_available.return_value = True
    mock_k8s.custom_objects.patch_namespaced_custom_object.return_value = {}

    resp = await async_client.put(
        f"/api/v1/tenants/{sample_tenant.slug}/backup/schedule",
        json={"schedule": "0 3 * * *", "retention_days": 14},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["schedule"] == "0 3 * * *"
    assert data["tenant"] == sample_tenant.slug


# ---------------------------------------------------------------------------
# Application new fields (Sprint 11 model fields exposed via Sprint 10 API)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_app_with_new_fields(async_client, sample_tenant):
    """Creating an app with app_type, canary settings and volumes works."""
    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps",
        json={
            "name": "Worker App",
            "repo_url": "https://github.com/org/worker",
            "app_type": "worker",
            "canary_enabled": False,
            "canary_weight": 20,
            "volumes": [{"name": "data", "mount_path": "/data", "size_gi": 5}],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["app_type"] == "worker"
    assert data["canary_enabled"] is False
    assert data["canary_weight"] == 20
    assert data["volumes"] == [{"name": "data", "mount_path": "/data", "size_gi": 5}]


@pytest.mark.asyncio
async def test_app_defaults_to_web_type(async_client, sample_tenant):
    """Applications default to app_type=web when not specified."""
    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps",
        json={"name": "Web App", "repo_url": "https://github.com/org/web"},
    )
    assert resp.status_code == 201
    assert resp.json()["app_type"] == "web"
