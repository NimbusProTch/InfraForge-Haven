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
    REDIS = "redis"
    RABBITMQ = "rabbitmq"


class ServiceTier(PyEnum):
    DEV = "dev"
    PROD = "prod"


class ServiceStatus(PyEnum):
    PROVISIONING = "provisioning"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"


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

    tenant: Mapped["Tenant"] = relationship(back_populates="services")
