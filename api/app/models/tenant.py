import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.application import Application


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    namespace: Mapped[str] = mapped_column(String(63), unique=True)
    keycloak_realm: Mapped[str] = mapped_column(String(255))

    # Resource quotas
    cpu_limit: Mapped[str] = mapped_column(String(20), default="16")
    memory_limit: Mapped[str] = mapped_column(String(20), default="32Gi")
    storage_limit: Mapped[str] = mapped_column(String(20), default="100Gi")

    active: Mapped[bool] = mapped_column(Boolean, default=True)

    applications: Mapped[list["Application"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
