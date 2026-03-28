import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.deployment import Deployment


class EnvironmentType(StrEnum):
    production = "production"
    staging = "staging"
    preview = "preview"


class EnvironmentStatus(StrEnum):
    pending = "pending"
    building = "building"
    running = "running"
    failed = "failed"
    deleting = "deleting"


class Environment(Base, TimestampMixin):
    """A named deployment environment for an application (production/staging/PR preview)."""

    __tablename__ = "environments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    # Unique within an application: "production", "staging", "pr-42"
    name: Mapped[str] = mapped_column(String(63), index=True)
    env_type: Mapped[EnvironmentType] = mapped_column(
        Enum(EnvironmentType, values_callable=lambda e: [x.value for x in e]),
        default=EnvironmentType.production,
    )
    # Branch to deploy for this environment
    branch: Mapped[str] = mapped_column(String(255), default="main")
    # Current deployment status
    status: Mapped[EnvironmentStatus] = mapped_column(
        Enum(EnvironmentStatus, values_callable=lambda e: [x.value for x in e]),
        default=EnvironmentStatus.pending,
    )
    # PR number — only set for preview environments
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Environment-specific env var overrides (merged on top of app env_vars)
    env_vars: Mapped[dict] = mapped_column(JSON, default=dict)
    # Replica override — None means use app default
    replicas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Computed URL for this environment
    domain: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # K8s namespace override (auto-computed if None)
    namespace_override: Mapped[str | None] = mapped_column(String(63), nullable=True)
    # Last successfully built image tag
    last_image_tag: Mapped[str | None] = mapped_column(String(512), nullable=True)

    application: Mapped["Application"] = relationship(back_populates="environments")
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="environment", cascade="all, delete-orphan"
    )
