"""Access request submissions from the public /auth/request-access form.

Context
-------
iyziops is positioned as an **enterprise-only** platform — no self-signup.
Prospective customers land on the public landing page, fill out a short
form ("I'd like access"), and wait for a platform administrator to
approve + provision them.

This model stores the inbound request. It is anonymous-writable (rate
limited + honeypot on the router side) and platform_admin-readable.

Lifecycle
---------

  pending  →  approved  (platform admin clicked "Approve & Provision")
           →  rejected  (platform admin declined, optional reason)

The approval flow (in admin_tenants router) creates:
  1. Keycloak user in the shared `haven` realm
  2. Tenant + TenantMember(owner) for the requester
  3. execute-actions-email to the requester (set password)

and flips this row's status to `approved` + stamps reviewed_by/at.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AccessRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AccessRequest(Base, TimestampMixin):
    __tablename__ = "access_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Submitter-provided fields (anonymous writer — validate server-side)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320), index=True)  # RFC 5321 max
    org_name: Mapped[str] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Platform-side workflow
    status: Mapped[AccessRequestStatus] = mapped_column(
        Enum(AccessRequestStatus, name="accessrequeststatus", values_callable=lambda e: [v.value for v in e]),
        default=AccessRequestStatus.PENDING,
        index=True,
    )
    # Keycloak `sub` of the platform admin who approved/rejected.
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Free-form decision note (e.g. rejection reason, provisioned tenant slug)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Simple fraud-audit trail
    submitter_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max

    __table_args__ = (Index("ix_access_requests_status_created", "status", "created_at"),)
