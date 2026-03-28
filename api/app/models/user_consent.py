import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if False:  # TYPE_CHECKING
    from app.models.tenant import Tenant


class ConsentType(str, enum.Enum):
    data_processing = "data_processing"       # GDPR Art. 6(1)(a) — lawful basis
    marketing = "marketing"                   # opt-in marketing emails
    analytics = "analytics"                   # usage analytics / telemetry
    third_party_sharing = "third_party_sharing"  # data shared with third parties
    data_retention = "data_retention"         # extended retention beyond minimum


class UserConsent(Base, TimestampMixin):
    """Tracks GDPR consent grants and revocations per user per tenant.

    GDPR Art. 7 requires controllers to demonstrate that consent was given.
    Each record is immutable — revocation creates a new record with revoked_at set.
    """

    __tablename__ = "user_consents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    # Keycloak user subject (sub claim from JWT)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    consent_type: Mapped[ConsentType] = mapped_column(
        Enum(ConsentType, values_callable=lambda e: [x.value for x in e]),
        index=True,
    )
    granted: Mapped[bool] = mapped_column(default=True)
    # IP address at time of consent (GDPR Art. 7 — proof of consent)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Free-text context (e.g. "accepted DPA v2.1 on signup flow")
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Populated when this record is a revocation
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="consents")
