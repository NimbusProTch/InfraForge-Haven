"""Tests for the observability endpoints (pods + events)."""

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_pod(name: str, phase: str = "Running", restarts: int = 0, node: str = "worker-1"):
    pod = MagicMock()
    pod.metadata.name = name
    pod.metadata.creation_timestamp = None
    pod.status.phase = phase
    pod.spec.node_name = node

    cs = MagicMock()
    cs.restart_count = restarts
    cs.state.waiting = None
    cs.state.terminated = None
    pod.status.container_statuses = [cs]

    return pod


def _make_mock_event(obj_name: str, reason: str = "Pulled", msg: str = "Image pulled", ev_type: str = "Normal"):
    ev = MagicMock()
    ev.involved_object.name = obj_name
    ev.reason = reason
    ev.message = msg
    ev.type = ev_type
    ev.count = 1
    ev.first_timestamp = None
    ev.last_timestamp = None
    return ev


# ---------------------------------------------------------------------------
# /pods tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pods_cluster_unavailable(async_client, mock_k8s, tenant_with_app):
    """When cluster is unavailable, returns empty pod list with k8s_available=False."""
    mock_k8s.is_available.return_value = False
    tenant, _ = tenant_with_app

    resp = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/my-app/pods")
    assert resp.status_code == 200
    data = resp.json()
    assert data["k8s_available"] is False
    assert data["pods"] == []


@pytest.mark.asyncio
async def test_pods_no_pods_running(async_client, mock_k8s, tenant_with_app):
    """When cluster is available but no pods exist, returns empty pod list."""
    mock_k8s.is_available.return_value = True

    pod_list = MagicMock()
    pod_list.items = []
    mock_k8s.core_v1.list_namespaced_pod.return_value = pod_list
    mock_k8s.custom_objects.list_namespaced_custom_object.side_effect = Exception("no metrics")

    tenant, _ = tenant_with_app
    resp = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/my-app/pods")
    assert resp.status_code == 200
    data = resp.json()
    assert data["k8s_available"] is True
    assert data["pods"] == []


@pytest.mark.asyncio
async def test_pods_running_without_metrics(async_client, mock_k8s, tenant_with_app):
    """Pods returned correctly when metrics-server is unavailable."""
    mock_k8s.is_available.return_value = True

    pod_list = MagicMock()
    pod_list.items = [
        _make_mock_pod("my-app-abc123-xyz", phase="Running", restarts=0),
        _make_mock_pod("my-app-abc123-def", phase="Running", restarts=2),
    ]
    mock_k8s.core_v1.list_namespaced_pod.return_value = pod_list
    mock_k8s.custom_objects.list_namespaced_custom_object.side_effect = Exception("no metrics")

    tenant, _ = tenant_with_app
    resp = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/my-app/pods")
    assert resp.status_code == 200
    data = resp.json()
    assert data["k8s_available"] is True
    assert len(data["pods"]) == 2

    pod0 = data["pods"][0]
    assert pod0["name"] == "my-app-abc123-xyz"
    assert pod0["status"] == "Running"
    assert pod0["restarts"] == 0
    assert pod0["cpu_value"] is None
    assert pod0["memory_value"] is None

    assert data["pods"][1]["restarts"] == 2


@pytest.mark.asyncio
async def test_pods_with_metrics(async_client, mock_k8s, tenant_with_app):
    """CPU/memory values and percentages populated when metrics-server is available."""
    mock_k8s.is_available.return_value = True

    pod_list = MagicMock()
    pod_list.items = [_make_mock_pod("my-app-abc123-xyz", phase="Running")]
    mock_k8s.core_v1.list_namespaced_pod.return_value = pod_list

    mock_k8s.custom_objects.list_namespaced_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "my-app-abc123-xyz"},
                "containers": [{"usage": {"cpu": "42m", "memory": "128Mi"}}],
            }
        ]
    }

    tenant, _ = tenant_with_app
    resp = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/my-app/pods")
    assert resp.status_code == 200
    pod = resp.json()["pods"][0]
    assert pod["cpu_value"] == "42m"
    assert pod["memory_value"] == "128Mi"
    # 42m / 500m * 100 = 8%
    assert pod["cpu_usage"] == 8
    # 128Mi / 256Mi * 100 = 50%
    assert pod["memory_usage"] == 50


@pytest.mark.asyncio
async def test_pods_tenant_not_found(async_client):
    resp = await async_client.get("/api/v1/tenants/nonexistent/apps/some-app/pods")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pods_app_not_found(async_client, tenant_with_app):
    tenant, _ = tenant_with_app
    resp = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/nonexistent/pods")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /events tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_cluster_unavailable(async_client, mock_k8s, tenant_with_app):
    mock_k8s.is_available.return_value = False
    tenant, _ = tenant_with_app

    resp = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/my-app/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["k8s_available"] is False
    assert data["events"] == []


@pytest.mark.asyncio
async def test_events_filters_by_app_slug(async_client, mock_k8s, tenant_with_app):
    """Only events whose object name starts with the app slug are returned."""
    mock_k8s.is_available.return_value = True

    event_list = MagicMock()
    event_list.items = [
        _make_mock_event("my-app-abc123", reason="Pulling", msg="Pulling image", ev_type="Normal"),
        _make_mock_event("other-app-xyz", reason="Killing", msg="Stopping", ev_type="Warning"),
        _make_mock_event("my-app-abc123", reason="BackOff", msg="Crash loop", ev_type="Warning"),
    ]
    mock_k8s.core_v1.list_namespaced_event.return_value = event_list

    tenant, _ = tenant_with_app
    resp = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/my-app/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["k8s_available"] is True
    # 2 events for "my-app-*" (not the other-app one)
    assert len(data["events"]) == 2
    for ev in data["events"]:
        assert ev["object_name"].startswith("my-app")


@pytest.mark.asyncio
async def test_events_respects_limit(async_client, mock_k8s, tenant_with_app):
    mock_k8s.is_available.return_value = True

    event_list = MagicMock()
    event_list.items = [_make_mock_event("my-app-pod", reason=f"Reason{i}", ev_type="Warning") for i in range(30)]
    mock_k8s.core_v1.list_namespaced_event.return_value = event_list

    tenant, _ = tenant_with_app
    resp = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/my-app/events?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()["events"]) == 5
