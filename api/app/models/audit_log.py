"""AuditLog model — immutable record of every platform action."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    # Keycloak sub or "system" for background tasks
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Dot-separated action: "app.create", "deploy.trigger", "tenant.delete", …
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Extra context (request body, old values, etc.)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # IPv4 or IPv6, max 45 chars
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="audit_logs")
