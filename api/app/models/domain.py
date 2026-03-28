import enum
import secrets
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.application import Application


def _generate_verification_token() -> str:
    return secrets.token_hex(24)


class CertificateStatus(str, enum.Enum):
    pending = "pending"
    issuing = "issuing"
    issued = "issued"
    failed = "failed"


class DomainVerification(Base, TimestampMixin):
    __tablename__ = "domain_verifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)

    # The custom domain (e.g. "myapp.example.com")
    domain: Mapped[str] = mapped_column(String(255), index=True)

    # TXT record token for DNS ownership verification
    # User must add: _haven-verify.{domain} TXT {verification_token}
    verification_token: Mapped[str] = mapped_column(
        String(64), default=_generate_verification_token
    )

    # When the domain was verified via DNS TXT check
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # cert-manager Certificate resource status
    certificate_status: Mapped[CertificateStatus] = mapped_column(
        Enum(CertificateStatus, values_callable=lambda e: [x.value for x in e]),
        default=CertificateStatus.pending,
    )
    certificate_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    certificate_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    application: Mapped["Application"] = relationship(back_populates="domains")
