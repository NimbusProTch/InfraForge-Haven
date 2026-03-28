import secrets
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.deployment import Deployment
    from app.models.environment import Environment
    from app.models.tenant import Tenant


def _generate_webhook_token() -> str:
    return secrets.token_hex(32)


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
    webhook_token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=_generate_webhook_token
    )

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

    tenant: Mapped["Tenant"] = relationship(back_populates="applications")
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    environments: Mapped[list["Environment"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
