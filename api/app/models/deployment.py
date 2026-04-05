import uuid
from enum import StrEnum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.environment import Environment


class DeploymentStatus(PyEnum):
    PENDING = "pending"
    BUILDING = "building"
    DEPLOYING = "deploying"
    RUNNING = "running"
    FAILED = "failed"


class Deployment(Base, TimestampMixin):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    # Optional — set for environment-scoped deployments (staging/preview)
    environment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(40))
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, values_callable=lambda e: [x.value for x in e]),
        default=DeploymentStatus.PENDING,
        index=True,
    )
    build_job_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_tag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    gitops_commit_sha: Mapped[str | None] = mapped_column(String(255), nullable=True)

    application: Mapped["Application"] = relationship(back_populates="deployments")
    environment: Mapped["Environment | None"] = relationship(back_populates="deployments")


class BuildJob(Base, TimestampMixin):
    __tablename__ = "build_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deployments.id"), index=True)
    k8s_job_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)
