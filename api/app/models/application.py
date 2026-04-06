import secrets
import uuid
from enum import StrEnum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.cluster import Cluster
    from app.models.cronjob import CronJob
    from app.models.deployment import Deployment
    from app.models.domain import DomainVerification
    from app.models.environment import Environment
    from app.models.tenant import Tenant


def _generate_webhook_token() -> str:
    return secrets.token_hex(32)


class AppType(PyEnum):
    WEB = "web"
    WORKER = "worker"
    CRONJOB = "cronjob"


class Application(Base, TimestampMixin):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    slug: Mapped[str] = mapped_column(String(63), index=True)
    name: Mapped[str] = mapped_column(String(255))
    repo_url: Mapped[str] = mapped_column(String(2048))
    branch: Mapped[str] = mapped_column(String(255), default="main")
    env_vars: Mapped[dict] = mapped_column(JSON, default=dict)
    image_tag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    replicas: Mapped[int] = mapped_column(default=1)
    port: Mapped[int] = mapped_column(default=8000)
    # Unique token used to route GitHub webhooks to this application
    webhook_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=_generate_webhook_token)

    # Sprint 3: Monorepo support
    dockerfile_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    build_context: Mapped[str | None] = mapped_column(String(512), nullable=True)
    use_dockerfile: Mapped[bool] = mapped_column(Boolean, default=False)
    detected_deps: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Sprint 6: Production hardening
    custom_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    health_check_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    resource_cpu_request: Mapped[str] = mapped_column(String(32), default="50m")
    resource_cpu_limit: Mapped[str] = mapped_column(String(32), default="500m")
    resource_memory_request: Mapped[str] = mapped_column(String(32), default="64Mi")
    resource_memory_limit: Mapped[str] = mapped_column(String(32), default="512Mi")
    min_replicas: Mapped[int] = mapped_column(Integer, default=1)
    max_replicas: Mapped[int] = mapped_column(Integer, default=5)
    cpu_threshold: Mapped[int] = mapped_column(Integer, default=70)
    auto_deploy: Mapped[bool] = mapped_column(Boolean, default=True)

    # Sprint 11: App type
    app_type: Mapped[str] = mapped_column(
        Enum(AppType, values_callable=lambda e: [x.value for x in e]),
        default=AppType.WEB.value,
    )

    # Sprint 11: Canary deploy
    canary_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    canary_weight: Mapped[int] = mapped_column(Integer, default=10)

    # Sprint 11: Persistent volumes (JSON array of {name, mount_path, size_gi})
    volumes: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)

    # Sprint 12: target cluster for region-aware deployment
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clusters.id"), nullable=True, index=True)

    # Managed service connections: [{service_name, secret_name, namespace}]
    env_from_secrets: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)

    # Services requested during app creation, awaiting provisioning + auto-connect
    # [{service_name, service_type}] — cleared as each service reaches READY and is connected
    pending_services: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)

    tenant: Mapped["Tenant"] = relationship(back_populates="applications")
    deployments: Mapped[list["Deployment"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    environments: Mapped[list["Environment"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    domains: Mapped[list["DomainVerification"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    cronjobs: Mapped[list["CronJob"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    cluster: Mapped["Cluster | None"] = relationship(back_populates="applications", foreign_keys=[cluster_id])
