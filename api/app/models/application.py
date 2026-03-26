import secrets
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.deployment import Deployment
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

    tenant: Mapped["Tenant"] = relationship(back_populates="applications")
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
