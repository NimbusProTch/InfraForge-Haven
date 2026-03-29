import uuid
from enum import StrEnum

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class OrgPlan(StrEnum):
    free = "free"
    starter = "starter"
    pro = "pro"
    enterprise = "enterprise"


class OrgMemberRole(StrEnum):
    owner = "owner"
    admin = "admin"
    member = "member"
    billing = "billing"  # can only view/manage billing


class SSOType(StrEnum):
    oidc = "oidc"
    saml = "saml"


class Organization(Base, TimestampMixin):
    """Groups one or more tenants under a single billing and SSO unit."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    plan: Mapped[OrgPlan] = mapped_column(
        Enum(OrgPlan, values_callable=lambda e: [x.value for x in e]),
        default=OrgPlan.free,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Billing aggregation fields
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Privacy-by-default: no marketing, no analytics unless explicitly enabled
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    analytics_consent: Mapped[bool] = mapped_column(Boolean, default=False)

    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    sso_configs: Mapped[list["SSOConfig"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    tenant_memberships: Mapped[list["OrgTenantMembership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationMember(Base, TimestampMixin):
    """A user's membership in an organization."""

    __tablename__ = "organization_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    # Keycloak user subject (sub claim from JWT)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    email: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[OrgMemberRole] = mapped_column(
        Enum(OrgMemberRole, values_callable=lambda e: [x.value for x in e]),
        default=OrgMemberRole.member,
    )

    organization: Mapped["Organization"] = relationship(back_populates="members")


class SSOConfig(Base, TimestampMixin):
    """SAML / OIDC identity provider configuration for an organization.

    Keycloak identity brokering is used to federate external IdPs.
    One active SSO config per org at a time (though multiple can exist for migration).
    """

    __tablename__ = "sso_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    sso_type: Mapped[SSOType] = mapped_column(Enum(SSOType, values_callable=lambda e: [x.value for x in e]))
    # OIDC fields
    client_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    client_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    discovery_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # SAML fields
    metadata_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    metadata_xml: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Keycloak identity provider alias (set after Keycloak Admin API call)
    keycloak_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # If true, org members MUST use SSO — email/password login is disabled
    sso_only: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    organization: Mapped["Organization"] = relationship(back_populates="sso_configs")


class OrgTenantMembership(Base, TimestampMixin):
    """Links a Tenant to an Organization (many-to-many through this table)."""

    __tablename__ = "org_tenant_memberships"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(String(36), index=True)

    organization: Mapped["Organization"] = relationship(back_populates="tenant_memberships")
