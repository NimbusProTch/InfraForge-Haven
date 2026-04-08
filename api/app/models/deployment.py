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
    BUILT = "built"
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


# H3b (P2.2): The `BuildJob` model used to live here. It carried a TODO
# "Remove unused model — replaced by K8s Job direct API" since the build
# pipeline switched to submitting K8s Jobs directly via the Kubernetes
# Python client (no DB row to mirror them). It had zero production callers
# (only `tests/test_build_queue.py` referenced the unrelated
# `BuildJobStatus` Redis-queue enum from `services/build_queue_service.py`).
#
# Sprint H3 deleted the model. The corresponding `build_jobs` table is
# dropped in Alembic migration 0022.
#
# `BuildJobResponse` schema was likewise dead and removed from
# `app/schemas/deployment.py`.
