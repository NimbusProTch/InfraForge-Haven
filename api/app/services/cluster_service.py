"""Cluster management service — CRUD, health checks, and failover logic."""

import logging
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster, ClusterStatus
from app.schemas.cluster import ClusterCreate, ClusterUpdate

logger = logging.getLogger(__name__)

# Timeout for cluster API health probes (seconds)
_HEALTH_PROBE_TIMEOUT = 5.0


class ClusterService:
    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def list_clusters(self, db: AsyncSession) -> list[Cluster]:
        result = await db.execute(select(Cluster).order_by(Cluster.is_primary.desc(), Cluster.name))
        return list(result.scalars().all())

    async def get_cluster(self, cluster_id: uuid.UUID, db: AsyncSession) -> Cluster | None:
        result = await db.execute(select(Cluster).where(Cluster.id == cluster_id))
        return result.scalar_one_or_none()

    async def get_cluster_by_name(self, name: str, db: AsyncSession) -> Cluster | None:
        result = await db.execute(select(Cluster).where(Cluster.name == name))
        return result.scalar_one_or_none()

    async def get_primary_cluster(self, db: AsyncSession) -> Cluster | None:
        result = await db.execute(select(Cluster).where(Cluster.is_primary.is_(True)))
        return result.scalar_one_or_none()

    async def get_clusters_by_region(self, region: str, db: AsyncSession) -> list[Cluster]:
        result = await db.execute(
            select(Cluster).where(Cluster.region == region).order_by(Cluster.is_primary.desc())
        )
        return list(result.scalars().all())

    async def create_cluster(self, body: ClusterCreate, db: AsyncSession) -> Cluster:
        # If new cluster is primary, demote existing primary
        if body.is_primary:
            await self._demote_existing_primary(db)

        cluster = Cluster(
            name=body.name,
            region=body.region,
            region_label=body.region_label,
            provider=body.provider.value,
            api_endpoint=body.api_endpoint,
            kubeconfig_secret=body.kubeconfig_secret,
            kubeconfig_data=body.kubeconfig_data,
            is_primary=body.is_primary,
            schedulable=body.schedulable,
            failover_cluster_id=body.failover_cluster_id,
            status=ClusterStatus.unknown.value,
        )
        db.add(cluster)
        await db.commit()
        await db.refresh(cluster)
        logger.info("Created cluster '%s' in region '%s'", cluster.name, cluster.region)
        return cluster

    async def update_cluster(self, cluster: Cluster, body: ClusterUpdate, db: AsyncSession) -> Cluster:
        # Handle primary promotion
        if body.is_primary is True and not cluster.is_primary:
            await self._demote_existing_primary(db)

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            nullable_fields = ("kubeconfig_data", "kubeconfig_secret", "failover_cluster_id")
            if (value is not None or field in nullable_fields) and hasattr(cluster, field):
                # Store enum value as string
                if field in ("provider", "status") and hasattr(value, "value"):
                    value = value.value
                setattr(cluster, field, value)

        await db.commit()
        await db.refresh(cluster)
        return cluster

    async def delete_cluster(self, cluster: Cluster, db: AsyncSession) -> None:
        await db.delete(cluster)
        await db.commit()
        logger.info("Deleted cluster '%s'", cluster.name)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def check_cluster_health(self, cluster: Cluster, db: AsyncSession) -> Cluster:
        """Probe the cluster's API endpoint and update status."""
        status, message, node_count = await self._probe_cluster(cluster)

        cluster.status = status.value
        cluster.health_message = message
        cluster.last_health_check = datetime.now(tz=UTC)
        if node_count is not None:
            cluster.node_count = node_count

        await db.commit()
        await db.refresh(cluster)
        logger.info(
            "Cluster '%s' health check: status=%s nodes=%s",
            cluster.name,
            status.value,
            node_count,
        )
        return cluster

    async def check_all_clusters(self, db: AsyncSession) -> list[Cluster]:
        """Run health checks on all registered clusters."""
        clusters = await self.list_clusters(db)
        results = []
        for cluster in clusters:
            results.append(await self.check_cluster_health(cluster, db))
        return results

    async def _probe_cluster(
        self, cluster: Cluster
    ) -> tuple[ClusterStatus, str, int | None]:
        """Make an HTTP probe to the cluster API endpoint.

        Returns (status, message, node_count).
        node_count is None when the endpoint is unreachable or unauthenticated.
        """
        url = cluster.api_endpoint.rstrip("/")
        # Attempt /healthz (unauthenticated probe supported by most K8s clusters)
        healthz_url = f"{url}/healthz"
        try:
            async with httpx.AsyncClient(verify=False, timeout=_HEALTH_PROBE_TIMEOUT) as client:
                resp = await client.get(healthz_url)
            if resp.status_code == 200:
                return ClusterStatus.active, "Cluster API reachable", None
            return (
                ClusterStatus.degraded,
                f"Cluster API returned HTTP {resp.status_code}",
                None,
            )
        except httpx.TimeoutException:
            return ClusterStatus.degraded, "Cluster API probe timed out", None
        except Exception as exc:  # noqa: BLE001
            return ClusterStatus.unknown, f"Cluster API unreachable: {exc}", None

    # ------------------------------------------------------------------
    # Failover
    # ------------------------------------------------------------------

    async def get_failover_cluster(self, cluster: Cluster, db: AsyncSession) -> Cluster | None:
        """Return the configured failover cluster for the given cluster."""
        if cluster.failover_cluster_id is None:
            return None
        try:
            fid = uuid.UUID(str(cluster.failover_cluster_id))
        except ValueError:
            return None
        return await self.get_cluster(fid, db)

    async def resolve_deployment_cluster(
        self, preferred_cluster_id: uuid.UUID | None, db: AsyncSession
    ) -> Cluster | None:
        """Resolve which cluster to deploy to.

        Strategy:
        1. If preferred_cluster_id is specified and the cluster is active + schedulable → use it.
        2. If preferred cluster is degraded/unknown, try its failover cluster.
        3. Fall back to primary cluster.
        4. Fall back to any active + schedulable cluster.
        """
        if preferred_cluster_id is not None:
            preferred = await self.get_cluster(preferred_cluster_id, db)
            if preferred and preferred.status == ClusterStatus.active.value and preferred.schedulable:
                return preferred
            # Try failover
            if preferred:
                failover = await self.get_failover_cluster(preferred, db)
                if failover and failover.status == ClusterStatus.active.value and failover.schedulable:
                    logger.warning(
                        "Cluster '%s' unavailable, routing to failover '%s'",
                        preferred.name,
                        failover.name,
                    )
                    return failover

        # Fall back to primary
        primary = await self.get_primary_cluster(db)
        if primary and primary.status == ClusterStatus.active.value and primary.schedulable:
            return primary

        # Any active schedulable cluster
        result = await db.execute(
            select(Cluster)
            .where(Cluster.status == ClusterStatus.active.value, Cluster.schedulable.is_(True))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def trigger_failover(self, cluster: Cluster, db: AsyncSession) -> Cluster | None:
        """Mark a cluster as inactive and return its failover target (if any)."""
        cluster.status = ClusterStatus.inactive.value
        cluster.schedulable = False
        cluster.health_message = "Failover triggered — cluster marked inactive"
        cluster.last_health_check = datetime.now(tz=UTC)
        await db.commit()
        await db.refresh(cluster)
        logger.warning("Failover triggered for cluster '%s'", cluster.name)
        return await self.get_failover_cluster(cluster, db)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _demote_existing_primary(self, db: AsyncSession) -> None:
        existing = await self.get_primary_cluster(db)
        if existing:
            existing.is_primary = False
            await db.flush()


cluster_service = ClusterService()
