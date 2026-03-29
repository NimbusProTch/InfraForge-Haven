import uuid

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DataRetentionPolicy(Base, TimestampMixin):
    """Per-tenant configurable data retention periods.

    Governs how long different categories of data are kept before automatic deletion.
    Defaults match GDPR minimisation principle (Art. 5(1)(e)).
    """

    __tablename__ = "data_retention_policies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), unique=True, index=True)

    # Retention periods in days (0 = keep forever, -1 = delete immediately after use)
    audit_log_days: Mapped[int] = mapped_column(Integer, default=365)  # 1 year
    deployment_log_days: Mapped[int] = mapped_column(Integer, default=90)  # 3 months
    build_log_days: Mapped[int] = mapped_column(Integer, default=30)  # 1 month
    usage_record_days: Mapped[int] = mapped_column(Integer, default=730)  # 2 years (billing)
    inactive_app_days: Mapped[int] = mapped_column(Integer, default=180)  # 6 months

    # Human-readable description for the DPA / privacy notice
    policy_version: Mapped[str] = mapped_column(String(20), default="1.0")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
