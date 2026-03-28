import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.cluster import ClusterProvider, ClusterStatus


class ClusterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    region: str = Field(..., min_length=1, max_length=100)
    region_label: str = Field(default="")
    provider: ClusterProvider = ClusterProvider.hetzner
    api_endpoint: str = Field(..., min_length=1, max_length=512)
    kubeconfig_secret: str | None = None
    kubeconfig_data: str | None = None
    is_primary: bool = False
    schedulable: bool = True
    failover_cluster_id: uuid.UUID | None = None


class ClusterUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=100)
    region_label: str | None = None
    provider: ClusterProvider | None = None
    api_endpoint: str | None = Field(default=None, max_length=512)
    kubeconfig_secret: str | None = None
    kubeconfig_data: str | None = None
    is_primary: bool | None = None
    schedulable: bool | None = None
    status: ClusterStatus | None = None
    failover_cluster_id: uuid.UUID | None = None


class ClusterResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    region: str
    region_label: str
    provider: str
    api_endpoint: str
    kubeconfig_secret: str | None
    status: str
    is_primary: bool
    schedulable: bool
    last_health_check: datetime | None
    health_message: str | None
    node_count: int
    failover_cluster_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ClusterHealthResponse(BaseModel):
    cluster_id: uuid.UUID
    cluster_name: str
    status: str
    is_primary: bool
    schedulable: bool
    node_count: int
    last_health_check: datetime | None
    health_message: str | None


class RegionRoutingEntry(BaseModel):
    region: str
    cluster_id: uuid.UUID
    cluster_name: str
    is_primary: bool
    weight: int = 100
    dns_record: str | None = None


class MultiRegionRoutingResponse(BaseModel):
    regions: list[RegionRoutingEntry]
    primary_region: str | None
    total_clusters: int
