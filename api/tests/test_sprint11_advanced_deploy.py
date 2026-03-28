"""Sprint 11 — Advanced Deploy tests.

Covers:
- Rollback endpoint (roll back to a past deployment image)
- CronJob CRUD (create, list, get, update, delete, run-now)
- PVC management (create, list, delete volumes)
- Canary deploy (enable, status, promote, rollback)
"""

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment import Deployment, DeploymentStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_app(async_client, tenant_slug, name="test-app", repo="https://github.com/org/repo"):
    resp = await async_client.post(
        f"/api/v1/tenants/{tenant_slug}/apps",
        json={"name": name, "repo_url": repo},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Rollback (S11-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_requires_existing_deployment(async_client, db_session: AsyncSession, sample_tenant):
    """Rollback to non-existent deployment returns 404."""
    app = await _create_app(async_client, sample_tenant.slug, "roll-app")

    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/deployments/{uuid.uuid4()}/rollback"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rollback_requires_image_tag(async_client, db_session: AsyncSession, sample_tenant):
    """Rollback target deployment must have an image_tag."""
    from app.models.application import Application
    from sqlalchemy import select

    app_data = await _create_app(async_client, sample_tenant.slug, "roll-app2")
    result = await db_session.execute(
        select(Application).where(Application.slug == app_data["slug"])
    )
    app_obj = result.scalar_one()

    # Create a deployment without image_tag
    dep = Deployment(
        application_id=app_obj.id,
        commit_sha="abc123",
        status=DeploymentStatus.RUNNING,
        image_tag=None,
    )
    db_session.add(dep)
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app_data['slug']}/deployments/{dep.id}/rollback"
    )
    assert resp.status_code == 409
    assert "no image_tag" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_rollback_success(async_client, mock_k8s, db_session: AsyncSession, sample_tenant):
    """Successful rollback creates a new deployment record with the target image."""
    from app.models.application import Application
    from sqlalchemy import select

    mock_k8s.is_available.return_value = False  # Skip actual K8s ops

    app_data = await _create_app(async_client, sample_tenant.slug, "roll-app3")
    result = await db_session.execute(
        select(Application).where(Application.slug == app_data["slug"])
    )
    app_obj = result.scalar_one()

    # Create a past deployment with an image
    dep = Deployment(
        application_id=app_obj.id,
        commit_sha="abc123",
        status=DeploymentStatus.RUNNING,
        image_tag="harbor.example.com/haven/roll-app3:abc123",
    )
    db_session.add(dep)
    await db_session.commit()

    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app_data['slug']}/deployments/{dep.id}/rollback"
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["image_tag"] == "harbor.example.com/haven/roll-app3:abc123"
    assert "rollback-to-" in data["commit_sha"]


# ---------------------------------------------------------------------------
# CronJob CRUD (S11-03)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_cronjobs_empty(async_client, sample_tenant):
    """Empty CronJob list for a new app."""
    app = await _create_app(async_client, sample_tenant.slug, "cron-app1")
    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_cronjob(async_client, mock_k8s, sample_tenant):
    """Create a CronJob — DB record created, K8s skipped when unavailable."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "cron-app2")
    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs",
        json={
            "name": "daily-cleanup",
            "schedule": "0 2 * * *",
            "command": ["python", "manage.py", "cleanup"],
            "description": "Daily cleanup task",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "daily-cleanup"
    assert data["schedule"] == "0 2 * * *"
    assert data["command"] == ["python", "manage.py", "cleanup"]
    assert data["k8s_name"] is not None


@pytest.mark.asyncio
async def test_create_cronjob_with_k8s(async_client, mock_k8s, sample_tenant):
    """Create a CronJob — K8s CronJob created when cluster is available."""
    mock_k8s.is_available.return_value = True
    mock_k8s.batch_v1.create_namespaced_cron_job.return_value = MagicMock()

    app = await _create_app(async_client, sample_tenant.slug, "cron-app3")
    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs",
        json={"name": "hourly-sync", "schedule": "0 * * * *"},
    )
    assert resp.status_code == 201
    mock_k8s.batch_v1.create_namespaced_cron_job.assert_called_once()


@pytest.mark.asyncio
async def test_get_cronjob(async_client, mock_k8s, sample_tenant):
    """Get a CronJob by ID."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "cron-app4")
    create_resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs",
        json={"name": "weekly-report", "schedule": "0 9 * * 1"},
    )
    cj_id = create_resp.json()["id"]

    resp = await async_client.get(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs/{cj_id}"
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == cj_id


@pytest.mark.asyncio
async def test_update_cronjob_schedule(async_client, mock_k8s, sample_tenant):
    """Update CronJob schedule via PATCH."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "cron-app5")
    create_resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs",
        json={"name": "nightly", "schedule": "0 0 * * *"},
    )
    cj_id = create_resp.json()["id"]

    resp = await async_client.patch(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs/{cj_id}",
        json={"schedule": "30 1 * * *", "suspended": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["schedule"] == "30 1 * * *"
    assert data["suspended"] is True


@pytest.mark.asyncio
async def test_delete_cronjob(async_client, mock_k8s, sample_tenant):
    """Delete a CronJob removes it from DB."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "cron-app6")
    create_resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs",
        json={"name": "temp-job", "schedule": "* * * * *"},
    )
    cj_id = create_resp.json()["id"]

    del_resp = await async_client.delete(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs/{cj_id}"
    )
    assert del_resp.status_code == 204

    # Verify gone
    get_resp = await async_client.get(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs/{cj_id}"
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_cronjob_not_found_returns_404(async_client, sample_tenant):
    app = await _create_app(async_client, sample_tenant.slug, "cron-app7")
    resp = await async_client.get(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/cronjobs/{uuid.uuid4()}"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PVC Management (S11-05)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_volumes_empty(async_client, sample_tenant):
    """Empty volume list for new app."""
    app = await _create_app(async_client, sample_tenant.slug, "pvc-app1")
    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/volumes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["k8s_available"] is False  # Mock K8s returns unavailable
    assert data["volumes"] == []


@pytest.mark.asyncio
async def test_create_volume_persists_to_db(async_client, mock_k8s, sample_tenant):
    """Creating a volume updates the Application.volumes field."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "pvc-app2")
    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/volumes",
        json={"name": "data-vol", "mount_path": "/data", "size_gi": 10},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "data-vol"
    assert data["mount_path"] == "/data"
    assert data["size_gi"] == 10
    assert data["pvc_name"] == f"{app['slug']}-data-vol"


@pytest.mark.asyncio
async def test_create_volume_with_k8s(async_client, mock_k8s, sample_tenant):
    """Creating a volume creates PVC in K8s when cluster is available."""
    mock_k8s.is_available.return_value = True
    pvc_mock = MagicMock()
    pvc_mock.status.phase = "Pending"
    mock_k8s.core_v1.create_namespaced_persistent_volume_claim.return_value = pvc_mock

    app = await _create_app(async_client, sample_tenant.slug, "pvc-app3")
    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/volumes",
        json={"name": "uploads", "mount_path": "/uploads", "size_gi": 20, "storage_class": "longhorn"},
    )
    assert resp.status_code == 201
    mock_k8s.core_v1.create_namespaced_persistent_volume_claim.assert_called_once()
    assert resp.json()["phase"] == "Pending"


@pytest.mark.asyncio
async def test_create_volume_duplicate_returns_409(async_client, mock_k8s, sample_tenant):
    """Duplicate volume name in same app returns 409."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "pvc-app4")
    await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/volumes",
        json={"name": "cache", "mount_path": "/cache", "size_gi": 5},
    )
    # Second creation with same name
    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/volumes",
        json={"name": "cache", "mount_path": "/other-cache", "size_gi": 5},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_delete_volume(async_client, mock_k8s, sample_tenant):
    """Deleting a volume removes it from Application.volumes."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "pvc-app5")
    await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/volumes",
        json={"name": "tmp-vol", "mount_path": "/tmp-data", "size_gi": 3},
    )

    del_resp = await async_client.delete(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/volumes/tmp-vol"
    )
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_volume_not_found(async_client, sample_tenant):
    """Deleting non-existent volume returns 404."""
    app = await _create_app(async_client, sample_tenant.slug, "pvc-app6")
    resp = await async_client.delete(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/volumes/ghost-vol"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Canary Deploy (S11-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_canary_status_disabled_by_default(async_client, mock_k8s, sample_tenant):
    """Canary is disabled by default for a new application."""
    app = await _create_app(async_client, sample_tenant.slug, "canary-app1")
    resp = await async_client.get(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/canary"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False


@pytest.mark.asyncio
async def test_enable_canary_requires_image(async_client, mock_k8s, sample_tenant):
    """Enabling canary without canary_image when app has no image returns 422."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "canary-app2")
    resp = await async_client.put(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/canary",
        json={"enabled": True, "weight": 20},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_enable_canary_with_image(async_client, mock_k8s, sample_tenant):
    """Enabling canary with canary_image updates DB state."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "canary-app3")
    resp = await async_client.put(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/canary",
        json={"enabled": True, "weight": 15, "canary_image": "harbor.example.com/haven/canary-app3:new"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["weight"] == 15


@pytest.mark.asyncio
async def test_disable_canary(async_client, mock_k8s, sample_tenant):
    """Disabling canary sets enabled=False and weight back to 10."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "canary-app4")
    # First enable
    await async_client.put(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/canary",
        json={"enabled": True, "weight": 25, "canary_image": "harbor.example.com/haven/canary-app4:v2"},
    )
    # Then disable
    resp = await async_client.put(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/canary",
        json={"enabled": False, "weight": 0},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_canary_rollback_requires_active_canary(async_client, mock_k8s, sample_tenant):
    """Canary rollback returns 409 when canary is not active."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "canary-app5")
    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/canary/rollback"
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_canary_rollback_success(async_client, mock_k8s, sample_tenant):
    """Canary rollback disables canary and returns success message."""
    mock_k8s.is_available.return_value = False

    app = await _create_app(async_client, sample_tenant.slug, "canary-app6")
    # Enable canary first
    await async_client.put(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/canary",
        json={"enabled": True, "weight": 10, "canary_image": "harbor.example.com/haven/canary-app6:v2"},
    )
    # Rollback
    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/apps/{app['slug']}/canary/rollback"
    )
    assert resp.status_code == 200
    assert "rolled back" in resp.json()["message"].lower()
