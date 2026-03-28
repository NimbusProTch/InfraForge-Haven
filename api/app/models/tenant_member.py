import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class MemberRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


class TenantMember(Base, TimestampMixin):
    """Represents a user's membership in a tenant with a specific role."""

    __tablename__ = "tenant_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    # Keycloak user subject (sub claim from JWT)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    email: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, values_callable=lambda e: [x.value for x in e]),
        default=MemberRole.member,
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="members")
