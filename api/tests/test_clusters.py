"""Sprint 12 — Multi-cluster, Multi-region tests.

Covers:
  - Cluster CRUD endpoints (create, list, get, update, delete)
  - Cluster health check service logic
  - Failover resolution
  - Region-aware deployment routing
  - DNS routing table generation
  - Cross-cluster service discovery
  - Conflict and validation guards
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster, ClusterStatus


# ---------------------------------------------------------------------------
# Helper: create a cluster directly in DB
# ---------------------------------------------------------------------------


async def _make_cluster(
    db: AsyncSession,
    *,
    name: str = "test-cluster",
    region: str = "eu-west",
    api_endpoint: str = "https://k8s.example.com:6443",
    status: str = ClusterStatus.active.value,
    is_primary: bool = False,
    schedulable: bool = True,
    failover_cluster_id: uuid.UUID | None = None,
) -> Cluster:
    cluster = Cluster(
        id=uuid.uuid4(),
        name=name,
        region=region,
        region_label=f"EU West — {name}",
        provider="hetzner",
        api_endpoint=api_endpoint,
        status=status,
        is_primary=is_primary,
        schedulable=schedulable,
        node_count=3,
        failover_cluster_id=str(failover_cluster_id) if failover_cluster_id else None,
    )
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)
    return cluster


# ===========================================================================
# Cluster CRUD via API
# ===========================================================================


@pytest.mark.asyncio
async def test_list_clusters_empty(async_client):
    """GET /clusters returns empty list when no clusters registered."""
    resp = await async_client.get("/api/v1/clusters")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_cluster_success(async_client):
    """POST /clusters creates a new cluster and returns 201."""
    payload = {
        "name": "hetzner-fsn1",
        "region": "eu-north-de",
        "region_label": "Hetzner Falkenstein",
        "provider": "hetzner",
        "api_endpoint": "https://10.0.0.1:6443",
        "is_primary": True,
        "schedulable": True,
    }
    resp = await async_client.post("/api/v1/clusters", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "hetzner-fsn1"
    assert data["region"] == "eu-north-de"
    assert data["is_primary"] is True
    assert data["status"] == "unknown"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_cluster_duplicate_name(async_client):
    """POST /clusters with existing name returns 409."""
    payload = {
        "name": "duplicate-cluster",
        "region": "eu-west",
        "api_endpoint": "https://1.2.3.4:6443",
    }
    resp1 = await async_client.post("/api/v1/clusters", json=payload)
    assert resp1.status_code == 201

    resp2 = await async_client.post("/api/v1/clusters", json=payload)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_get_cluster_by_id(async_client, db_session):
    """GET /clusters/{id} returns the cluster."""
    cluster = await _make_cluster(db_session, name="get-test-cluster")
    resp = await async_client.get(f"/api/v1/clusters/{cluster.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "get-test-cluster"


@pytest.mark.asyncio
async def test_get_cluster_not_found(async_client):
    """GET /clusters/{unknown-id} returns 404."""
    resp = await async_client.get(f"/api/v1/clusters/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_cluster(async_client, db_session):
    """PATCH /clusters/{id} updates fields."""
    cluster = await _make_cluster(db_session, name="update-me", schedulable=True)
    resp = await async_client.patch(
        f"/api/v1/clusters/{cluster.id}",
        json={"schedulable": False, "region_label": "Updated Label"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["schedulable"] is False
    assert data["region_label"] == "Updated Label"


@pytest.mark.asyncio
async def test_delete_cluster_success(async_client, db_session):
    """DELETE /clusters/{id} removes cluster when no apps assigned."""
    cluster = await _make_cluster(db_session, name="delete-me")
    resp = await async_client.delete(f"/api/v1/clusters/{cluster.id}")
    assert resp.status_code == 204

    # Verify it's gone
    resp2 = await async_client.get(f"/api/v1/clusters/{cluster.id}")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_cluster_with_apps_blocked(async_client, db_session, tenant_with_app):
    """DELETE /clusters/{id} returns 409 when apps are still assigned."""
    cluster = await _make_cluster(db_session, name="cluster-with-apps")

    # Assign the existing app to this cluster
    tenant, app = tenant_with_app
    app.cluster_id = cluster.id
    await db_session.commit()

    resp = await async_client.delete(f"/api/v1/clusters/{cluster.id}")
    assert resp.status_code == 409
    assert "application" in resp.json()["detail"].lower()


# ===========================================================================
# Health check endpoint
# ===========================================================================


@pytest.mark.asyncio
async def test_health_check_marks_active(async_client, db_session):
    """POST /clusters/{id}/health-check marks cluster active when API reachable."""
    cluster = await _make_cluster(
        db_session, name="healthy-cluster", status=ClusterStatus.unknown.value
    )

    with patch(
        "app.services.cluster_service.ClusterService._probe_cluster",
        new_callable=AsyncMock,
        return_value=(ClusterStatus.active, "Cluster API reachable", 5),
    ):
        resp = await async_client.post(f"/api/v1/clusters/{cluster.id}/health-check")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["health_message"] == "Cluster API reachable"
    assert data["node_count"] == 5


@pytest.mark.asyncio
async def test_health_check_marks_degraded_on_timeout(async_client, db_session):
    """POST /clusters/{id}/health-check marks degraded when API times out."""
    cluster = await _make_cluster(db_session, name="slow-cluster")

    with patch(
        "app.services.cluster_service.ClusterService._probe_cluster",
        new_callable=AsyncMock,
        return_value=(ClusterStatus.degraded, "Cluster API probe timed out", None),
    ):
        resp = await async_client.post(f"/api/v1/clusters/{cluster.id}/health-check")

    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


# ===========================================================================
# Failover logic
# ===========================================================================


@pytest.mark.asyncio
async def test_failover_trigger_marks_cluster_inactive(async_client, db_session):
    """POST /clusters/{id}/failover marks the cluster inactive."""
    primary = await _make_cluster(db_session, name="primary-nl", is_primary=True)
    resp = await async_client.post(f"/api/v1/clusters/{primary.id}/failover")
    # Returns null when no failover cluster configured
    assert resp.status_code == 200

    # Verify cluster is now inactive
    check = await async_client.get(f"/api/v1/clusters/{primary.id}")
    assert check.json()["status"] == "inactive"
    assert check.json()["schedulable"] is False


@pytest.mark.asyncio
async def test_failover_routes_to_secondary(async_client, db_session):
    """POST /clusters/{id}/failover returns the configured failover cluster."""
    secondary = await _make_cluster(db_session, name="secondary-de", region="eu-north-de")
    primary = await _make_cluster(
        db_session,
        name="primary-nl",
        is_primary=True,
        failover_cluster_id=secondary.id,
    )

    resp = await async_client.post(f"/api/v1/clusters/{primary.id}/failover")
    assert resp.status_code == 200
    data = resp.json()
    assert data is not None
    assert data["name"] == "secondary-de"


# ===========================================================================
# Region routing
# ===========================================================================


@pytest.mark.asyncio
async def test_routing_table_empty(async_client):
    """GET /clusters/routing/table returns empty regions list when no clusters."""
    resp = await async_client.get("/api/v1/clusters/routing/table")
    assert resp.status_code == 200
    data = resp.json()
    assert data["regions"] == []
    assert data["primary_region"] is None
    assert data["total_clusters"] == 0


@pytest.mark.asyncio
async def test_routing_table_with_clusters(async_client, db_session):
    """Routing table returns one entry per region."""
    await _make_cluster(db_session, name="nl-primary", region="eu-west", is_primary=True)
    await _make_cluster(db_session, name="de-secondary", region="eu-north", is_primary=False)

    resp = await async_client.get("/api/v1/clusters/routing/table")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_clusters"] == 2
    regions = {e["region"] for e in data["regions"]}
    assert "eu-west" in regions
    assert "eu-north" in regions
    assert data["primary_region"] == "eu-west"


@pytest.mark.asyncio
async def test_best_cluster_for_region(async_client, db_session):
    """GET /clusters/routing/region/{region} returns active cluster in region."""
    await _make_cluster(
        db_session, name="ams-cluster", region="eu-west-nl", status=ClusterStatus.active.value
    )
    resp = await async_client.get("/api/v1/clusters/routing/region/eu-west-nl")
    assert resp.status_code == 200
    assert resp.json()["name"] == "ams-cluster"


@pytest.mark.asyncio
async def test_best_cluster_for_unknown_region(async_client):
    """GET /clusters/routing/region/{unknown} returns 404."""
    resp = await async_client.get("/api/v1/clusters/routing/region/ap-southeast-99")
    assert resp.status_code == 404


# ===========================================================================
# ClusterService unit tests
# ===========================================================================


@pytest.mark.asyncio
async def test_resolve_deployment_cluster_prefers_preferred(db_session):
    """resolve_deployment_cluster returns preferred cluster when active."""
    from app.services.cluster_service import ClusterService

    svc = ClusterService()
    cluster = await _make_cluster(db_session, name="preferred", status=ClusterStatus.active.value)

    result = await svc.resolve_deployment_cluster(cluster.id, db_session)
    assert result is not None
    assert result.id == cluster.id


@pytest.mark.asyncio
async def test_resolve_deployment_cluster_falls_back_to_failover(db_session):
    """When preferred cluster is degraded, failover cluster is selected."""
    from app.services.cluster_service import ClusterService

    svc = ClusterService()
    failover = await _make_cluster(
        db_session, name="failover-cluster", status=ClusterStatus.active.value
    )
    degraded = await _make_cluster(
        db_session,
        name="degraded-cluster",
        status=ClusterStatus.degraded.value,
        failover_cluster_id=failover.id,
    )

    result = await svc.resolve_deployment_cluster(degraded.id, db_session)
    assert result is not None
    assert result.id == failover.id


@pytest.mark.asyncio
async def test_resolve_deployment_cluster_falls_back_to_primary(db_session):
    """When preferred cluster is unknown and no failover, primary is used."""
    from app.services.cluster_service import ClusterService

    svc = ClusterService()
    primary = await _make_cluster(
        db_session, name="primary", is_primary=True, status=ClusterStatus.active.value
    )
    unknown_cluster = await _make_cluster(
        db_session, name="unknown-cluster", status=ClusterStatus.unknown.value
    )

    result = await svc.resolve_deployment_cluster(unknown_cluster.id, db_session)
    assert result is not None
    assert result.id == primary.id


# ===========================================================================
# DNS routing service unit tests
# ===========================================================================


def test_dns_routing_compute_weight_primary_active():
    from app.services.dns_routing_service import DnsRoutingService

    svc = DnsRoutingService()
    cluster = MagicMock()
    cluster.status = ClusterStatus.active.value
    cluster.is_primary = True
    assert svc._compute_traffic_weight(cluster) == 100


def test_dns_routing_compute_weight_secondary_active():
    from app.services.dns_routing_service import DnsRoutingService

    svc = DnsRoutingService()
    cluster = MagicMock()
    cluster.status = ClusterStatus.active.value
    cluster.is_primary = False
    assert svc._compute_traffic_weight(cluster) == 80


def test_dns_routing_compute_weight_degraded():
    from app.services.dns_routing_service import DnsRoutingService

    svc = DnsRoutingService()
    cluster = MagicMock()
    cluster.status = ClusterStatus.degraded.value
    cluster.is_primary = False
    assert svc._compute_traffic_weight(cluster) == 20


def test_dns_routing_build_dns_record_strips_scheme():
    from app.services.dns_routing_service import DnsRoutingService

    svc = DnsRoutingService()
    cluster = MagicMock()
    cluster.api_endpoint = "https://k8s-api.eu-west.example.com:6443"
    assert svc._build_dns_record(cluster) == "k8s-api.eu-west.example.com"


def test_dns_routing_cloudflare_config_structure(db_session):
    from app.schemas.cluster import MultiRegionRoutingResponse, RegionRoutingEntry
    from app.services.dns_routing_service import DnsRoutingService

    svc = DnsRoutingService()
    routing = MultiRegionRoutingResponse(
        regions=[
            RegionRoutingEntry(
                region="eu-west",
                cluster_id=uuid.uuid4(),
                cluster_name="nl-cluster",
                is_primary=True,
                weight=100,
                dns_record="10.0.0.1",
            )
        ],
        primary_region="eu-west",
        total_clusters=1,
    )
    config = svc.generate_cloudflare_load_balancer_config(routing, "apps.haven.example.com")
    assert config["name"] == "apps.haven.example.com"
    assert config["fallback_pool"] == "pool-eu-west"
    assert config["steering_policy"] == "geo"


@pytest.mark.asyncio
async def test_list_clusters_ordered_primary_first(async_client, db_session):
    """List endpoint returns primary cluster first."""
    await _make_cluster(db_session, name="secondary-cluster", is_primary=False)
    await _make_cluster(db_session, name="primary-cluster", is_primary=True)

    resp = await async_client.get("/api/v1/clusters")
    assert resp.status_code == 200
    clusters = resp.json()
    assert len(clusters) == 2
    assert clusters[0]["is_primary"] is True
    assert clusters[0]["name"] == "primary-cluster"
