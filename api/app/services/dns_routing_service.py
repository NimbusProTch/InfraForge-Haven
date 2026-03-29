"""Multi-region DNS routing service.

Provides logic for:
- Building a routing table per region (which cluster handles traffic for which region)
- Generating Cloudflare-compatible weighted DNS records for geo-routing
- Cross-cluster service discovery endpoint mapping
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster, ClusterStatus
from app.schemas.cluster import MultiRegionRoutingResponse, RegionRoutingEntry
from app.services.cluster_service import cluster_service

logger = logging.getLogger(__name__)


@dataclass
class ServiceEndpoint:
    """Represents a cross-cluster service endpoint."""

    service_name: str
    namespace: str
    cluster_name: str
    region: str
    internal_ip: str | None
    port: int
    protocol: str = "TCP"


class DnsRoutingService:
    """Manages multi-region DNS routing decisions."""

    async def get_routing_table(self, db: AsyncSession) -> MultiRegionRoutingResponse:
        """Build the complete multi-region routing table."""
        clusters = await cluster_service.list_clusters(db)

        # Group by region — pick the best cluster per region
        region_map: dict[str, Cluster] = {}
        for cluster in clusters:
            if not cluster.schedulable:
                continue
            existing = region_map.get(cluster.region)
            if existing is None:
                region_map[cluster.region] = cluster
            elif cluster.is_primary and not existing.is_primary:
                # Prefer primary cluster per region
                region_map[cluster.region] = cluster

        primary_region: str | None = None
        entries: list[RegionRoutingEntry] = []

        for region, cluster in sorted(region_map.items()):
            weight = self._compute_traffic_weight(cluster)
            dns_record = self._build_dns_record(cluster)
            entries.append(
                RegionRoutingEntry(
                    region=region,
                    cluster_id=cluster.id,
                    cluster_name=cluster.name,
                    is_primary=cluster.is_primary,
                    weight=weight,
                    dns_record=dns_record,
                )
            )
            if cluster.is_primary:
                primary_region = region

        return MultiRegionRoutingResponse(
            regions=entries,
            primary_region=primary_region,
            total_clusters=len(clusters),
        )

    async def get_best_cluster_for_region(self, region: str, db: AsyncSession) -> Cluster | None:
        """Return the healthiest schedulable cluster for the given region."""
        clusters = await cluster_service.get_clusters_by_region(region, db)
        # Prefer active primary, then active, then degraded
        for status_pref in (ClusterStatus.active, ClusterStatus.degraded):
            for cluster in clusters:
                if cluster.status == status_pref.value and cluster.schedulable:
                    return cluster
        return None

    def build_cross_cluster_endpoints(
        self, service_name: str, namespace: str, clusters: list[Cluster]
    ) -> list[ServiceEndpoint]:
        """Generate cross-cluster service discovery endpoints.

        In a real Cilium Cluster Mesh setup, these would map to
        GlobalService objects. Here we return the metadata so the
        caller can create the appropriate K8s/DNS records.
        """
        endpoints: list[ServiceEndpoint] = []
        for cluster in clusters:
            if cluster.status not in (ClusterStatus.active.value, ClusterStatus.degraded.value):
                continue
            # Derive the cluster-local service FQDN
            internal_ip = self._derive_cluster_dns(cluster.api_endpoint)
            endpoints.append(
                ServiceEndpoint(
                    service_name=service_name,
                    namespace=namespace,
                    cluster_name=cluster.name,
                    region=cluster.region,
                    internal_ip=internal_ip,
                    port=443,
                )
            )
        return endpoints

    def generate_cloudflare_load_balancer_config(
        self, routing_table: MultiRegionRoutingResponse, base_hostname: str
    ) -> dict:
        """Generate a Cloudflare Load Balancer config dict from the routing table.

        This is intended to be serialised and applied via the Cloudflare API
        (or Terraform cloudflare_load_balancer resource).
        """
        origins = []
        for entry in routing_table.regions:
            if entry.dns_record:
                origins.append(
                    {
                        "name": f"origin-{entry.region}",
                        "address": entry.dns_record,
                        "weight": entry.weight,
                        "enabled": True,
                    }
                )

        return {
            "name": base_hostname,
            "fallback_pool": f"pool-{routing_table.primary_region}" if routing_table.primary_region else None,
            "default_pools": [f"pool-{e.region}" for e in routing_table.regions],
            "pools": [
                {
                    "id": f"pool-{entry.region}",
                    "name": f"Haven {entry.region_label if hasattr(entry, 'region_label') else entry.region}",
                    "origins": [o for o in origins if entry.region in o["name"]],
                    "minimum_origins": 1,
                }
                for entry in routing_table.regions
            ],
            "steering_policy": "geo",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_traffic_weight(self, cluster: Cluster) -> int:
        """Assign traffic weight based on cluster health."""
        if cluster.status == ClusterStatus.active.value and cluster.is_primary:
            return 100
        if cluster.status == ClusterStatus.active.value:
            return 80
        if cluster.status == ClusterStatus.degraded.value:
            return 20
        return 0

    def _build_dns_record(self, cluster: Cluster) -> str | None:
        """Derive the external DNS record value from the cluster's API endpoint."""
        endpoint = cluster.api_endpoint
        # Strip scheme and port — return hostname/IP only
        for scheme in ("https://", "http://"):
            if endpoint.startswith(scheme):
                endpoint = endpoint[len(scheme) :]
        host = endpoint.split(":")[0]
        return host if host else None

    def _derive_cluster_dns(self, api_endpoint: str) -> str | None:
        """Extract the host portion of an API endpoint URL."""
        for scheme in ("https://", "http://"):
            if api_endpoint.startswith(scheme):
                api_endpoint = api_endpoint[len(scheme) :]
        return api_endpoint.split(":")[0] or None


dns_routing_service = DnsRoutingService()
