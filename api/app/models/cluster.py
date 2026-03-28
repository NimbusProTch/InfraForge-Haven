import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.application import Application


class ClusterStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    degraded = "degraded"
    unknown = "unknown"


class ClusterProvider(str, enum.Enum):
    hetzner = "hetzner"
    cyso = "cyso"
    leafcloud = "leafcloud"
    aws = "aws"
    azure = "azure"
    gcp = "gcp"
    other = "other"


class Cluster(Base, TimestampMixin):
    __tablename__ = "clusters"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    region: Mapped[str] = mapped_column(String(100), index=True)
    # e.g. "eu-west-nl", "eu-north-de"
    region_label: Mapped[str] = mapped_column(String(255), default="")
    provider: Mapped[str] = mapped_column(
        Enum(ClusterProvider, values_callable=lambda e: [x.value for x in e]),
        default=ClusterProvider.hetzner.value,
    )
    api_endpoint: Mapped[str] = mapped_column(String(512))
    # Reference to K8s Secret name holding the kubeconfig
    kubeconfig_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Inline kubeconfig (base64-encoded, encrypted in prod via SealedSecrets/Vault)
    kubeconfig_data: Mapped[str | None] = mapped_column(String(65535), nullable=True)

    status: Mapped[str] = mapped_column(
        Enum(ClusterStatus, values_callable=lambda e: [x.value for x in e]),
        default=ClusterStatus.unknown.value,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    # Whether this cluster accepts new workloads
    schedulable: Mapped[bool] = mapped_column(Boolean, default=True)

    # Health check metadata
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Approximate node count (updated by health check)
    node_count: Mapped[int] = mapped_column(default=0)

    # Failover config: if this cluster fails, route to failover_cluster_id
    failover_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        String(36), nullable=True
    )

    applications: Mapped[list["Application"]] = relationship(
        back_populates="cluster", foreign_keys="Application.cluster_id"
    )
