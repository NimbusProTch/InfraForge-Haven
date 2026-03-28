import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.application import Application


class CronJob(Base, TimestampMixin):
    __tablename__ = "cronjobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)

    # CronJob identity
    name: Mapped[str] = mapped_column(String(255))
    schedule: Mapped[str] = mapped_column(String(100))  # cron expression: "0 * * * *"

    # Command to run (overrides default image CMD)
    command: Mapped[list | None] = mapped_column(JSON, nullable=True)  # ["python", "manage.py", "task"]

    # Resource limits
    cpu_request: Mapped[str] = mapped_column(String(32), default="50m")
    cpu_limit: Mapped[str] = mapped_column(String(32), default="500m")
    memory_request: Mapped[str] = mapped_column(String(32), default="64Mi")
    memory_limit: Mapped[str] = mapped_column(String(32), default="256Mi")

    # K8s CronJob settings
    concurrency_policy: Mapped[str] = mapped_column(String(32), default="Forbid")  # Allow/Forbid/Replace
    successful_jobs_history: Mapped[int] = mapped_column(Integer, default=3)
    failed_jobs_history: Mapped[int] = mapped_column(Integer, default=1)
    starting_deadline_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # State
    suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    k8s_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # actual K8s resource name
    last_schedule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Environment variable overrides for this cron job
    env_vars: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped["Application"] = relationship(back_populates="cronjobs")
