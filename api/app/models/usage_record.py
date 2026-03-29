"""UsageRecord model — per-period billing metrics for a tenant."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # NULL means the period is still open (current period)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cpu_hours: Mapped[float] = mapped_column(Float, default=0.0)
    memory_gb_hours: Mapped[float] = mapped_column(Float, default=0.0)
    storage_gb_hours: Mapped[float] = mapped_column(Float, default=0.0)
    build_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    bandwidth_gb: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="usage_records")
