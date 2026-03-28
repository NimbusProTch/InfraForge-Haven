"""Cluster management endpoints — admin-only CRUD + health + routing."""

import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DBSession
from app.models.cluster import Cluster
from app.schemas.cluster import (
    ClusterCreate,
    ClusterHealthResponse,
    ClusterResponse,
    ClusterUpdate,
    MultiRegionRoutingResponse,
)
from app.services.cluster_service import cluster_service
from app.services.dns_routing_service import dns_routing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clusters", tags=["clusters"])


async def _get_cluster_or_404(cluster_id: uuid.UUID, db: DBSession) -> Cluster:
    cluster = await cluster_service.get_cluster(cluster_id, db)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return cluster


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ClusterResponse])
async def list_clusters(db: DBSession, current_user: CurrentUser) -> list[Cluster]:
    """List all registered clusters ordered by primary first, then name."""
    return await cluster_service.list_clusters(db)


@router.post("", response_model=ClusterResponse, status_code=status.HTTP_201_CREATED)
async def create_cluster(body: ClusterCreate, db: DBSession, current_user: CurrentUser) -> Cluster:
    """Register a new K8s cluster. If is_primary=True, the existing primary is demoted."""
    existing = await cluster_service.get_cluster_by_name(body.name, db)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Cluster '{body.name}' already exists")

    # Validate failover cluster reference
    if body.failover_cluster_id is not None:
        failover = await cluster_service.get_cluster(body.failover_cluster_id, db)
        if failover is None:
            raise HTTPException(status_code=422, detail="failover_cluster_id does not reference an existing cluster")

    return await cluster_service.create_cluster(body, db)


@router.get("/{cluster_id}", response_model=ClusterResponse)
async def get_cluster(cluster_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> Cluster:
    return await _get_cluster_or_404(cluster_id, db)


@router.patch("/{cluster_id}", response_model=ClusterResponse)
async def update_cluster(
    cluster_id: uuid.UUID, body: ClusterUpdate, db: DBSession, current_user: CurrentUser
) -> Cluster:
    cluster = await _get_cluster_or_404(cluster_id, db)
    return await cluster_service.update_cluster(cluster, body, db)


@router.delete("/{cluster_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cluster(cluster_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> None:
    cluster = await _get_cluster_or_404(cluster_id, db)
    # Prevent deleting a cluster that still has applications assigned
    from sqlalchemy import func

    from app.models.application import Application

    result = await db.execute(
        select(func.count()).select_from(Application).where(Application.cluster_id == cluster_id)
    )
    app_count = result.scalar_one()
    if app_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete cluster: {app_count} application(s) still assigned",
        )
    await cluster_service.delete_cluster(cluster, db)


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


@router.post("/{cluster_id}/health-check", response_model=ClusterHealthResponse)
async def run_health_check(cluster_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> ClusterHealthResponse:
    """Probe the cluster API endpoint and update health status."""
    cluster = await _get_cluster_or_404(cluster_id, db)
    updated = await cluster_service.check_cluster_health(cluster, db)
    return ClusterHealthResponse(
        cluster_id=updated.id,
        cluster_name=updated.name,
        status=updated.status,
        is_primary=updated.is_primary,
        schedulable=updated.schedulable,
        node_count=updated.node_count,
        last_health_check=updated.last_health_check,
        health_message=updated.health_message,
    )


@router.post("/health-check/all", response_model=list[ClusterHealthResponse])
async def run_all_health_checks(db: DBSession, current_user: CurrentUser) -> list[ClusterHealthResponse]:
    """Run health checks on every registered cluster."""
    clusters = await cluster_service.check_all_clusters(db)
    return [
        ClusterHealthResponse(
            cluster_id=c.id,
            cluster_name=c.name,
            status=c.status,
            is_primary=c.is_primary,
            schedulable=c.schedulable,
            node_count=c.node_count,
            last_health_check=c.last_health_check,
            health_message=c.health_message,
        )
        for c in clusters
    ]


# ---------------------------------------------------------------------------
# Failover
# ---------------------------------------------------------------------------


@router.post("/{cluster_id}/failover", response_model=ClusterResponse | None)
async def trigger_failover(cluster_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> Cluster | None:
    """Mark a cluster as inactive and return its configured failover cluster."""
    cluster = await _get_cluster_or_404(cluster_id, db)
    failover = await cluster_service.trigger_failover(cluster, db)
    if failover is None:
        logger.warning("No failover cluster configured for '%s'", cluster.name)
    return failover


# ---------------------------------------------------------------------------
# Multi-region routing
# ---------------------------------------------------------------------------


@router.get("/routing/table", response_model=MultiRegionRoutingResponse)
async def get_routing_table(db: DBSession, current_user: CurrentUser) -> MultiRegionRoutingResponse:
    """Return the multi-region routing table (one active cluster per region)."""
    return await dns_routing_service.get_routing_table(db)


@router.get("/routing/region/{region}", response_model=ClusterResponse | None)
async def get_best_cluster_for_region(region: str, db: DBSession, current_user: CurrentUser) -> Cluster | None:
    """Return the best available cluster for the requested region."""
    cluster = await dns_routing_service.get_best_cluster_for_region(region, db)
    if cluster is None:
        raise HTTPException(status_code=404, detail=f"No active cluster found in region '{region}'")
    return cluster
