import uuid
from enum import StrEnum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class ServiceType(PyEnum):
    POSTGRES = "postgres"
    MYSQL = "mysql"
    MONGODB = "mongodb"
    REDIS = "redis"
    RABBITMQ = "rabbitmq"
    KAFKA = "kafka"


class ServiceTier(PyEnum):
    DEV = "dev"
    PROD = "prod"


class ServiceStatus(PyEnum):
    PROVISIONING = "provisioning"
    READY = "ready"
    UPDATING = "updating"
    FAILED = "failed"
    DELETING = "deleting"
    DEGRADED = "degraded"


class ManagedService(Base, TimestampMixin):
    __tablename__ = "managed_services"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(63))  # user-given name, slug-safe
    service_type: Mapped[ServiceType] = mapped_column(
        Enum(ServiceType, values_callable=lambda obj: [e.value for e in obj])
    )
    tier: Mapped[ServiceTier] = mapped_column(
        Enum(ServiceTier, values_callable=lambda obj: [e.value for e in obj]),
        default=ServiceTier.DEV,
    )
    status: Mapped[ServiceStatus] = mapped_column(
        Enum(ServiceStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ServiceStatus.PROVISIONING,
    )
    # K8s secret name that holds the connection credentials
    secret_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # K8s namespace where the service CRD lives
    service_namespace: Mapped[str | None] = mapped_column(String(63), nullable=True)
    # Human-readable connection string (no password) for display
    connection_hint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Error message from Everest/K8s when provisioning or update fails
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Everest-managed DB name (prefixed with tenant slug for isolation)
    everest_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Custom database credentials (set by user or auto-generated)
    db_name: Mapped[str | None] = mapped_column(String(63), nullable=True)
    db_user: Mapped[str | None] = mapped_column(String(63), nullable=True)
    # True when custom user/db has been provisioned (prevents re-provisioning)
    credentials_provisioned: Mapped[bool] = mapped_column(default=False, server_default="0")

    tenant: Mapped["Tenant"] = relationship(back_populates="services")
