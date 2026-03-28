import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.organization import OrgMemberRole, OrgPlan, SSOType

# ---------------------------------------------------------------------------
# Organization schemas
# ---------------------------------------------------------------------------


class OrganizationCreate(BaseModel):
    slug: str = Field(..., min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    name: str = Field(..., min_length=1, max_length=255)
    plan: OrgPlan = OrgPlan.free

    @field_validator("slug")
    @classmethod
    def slug_no_reserved(cls, v: str) -> str:
        reserved = {"admin", "billing", "support", "haven", "platform"}
        if v in reserved:
            raise ValueError(f"Slug '{v}' is reserved")
        return v


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    plan: OrgPlan | None = None
    marketing_consent: bool | None = None
    analytics_consent: bool | None = None
    active: bool | None = None


class OrganizationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    slug: str
    name: str
    plan: OrgPlan
    active: bool
    marketing_consent: bool
    analytics_consent: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Organization member schemas
# ---------------------------------------------------------------------------


class OrgMemberInvite(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    role: OrgMemberRole = OrgMemberRole.member


class OrgMemberUpdate(BaseModel):
    role: OrgMemberRole


class OrgMemberResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: str
    email: str
    display_name: str | None
    role: OrgMemberRole
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# SSO config schemas
# ---------------------------------------------------------------------------


class SSOConfigCreate(BaseModel):
    sso_type: SSOType
    # OIDC fields
    client_id: str | None = Field(default=None, max_length=512)
    client_secret: str | None = Field(default=None, max_length=512)
    discovery_url: str | None = Field(default=None, max_length=2048)
    # SAML fields
    metadata_url: str | None = Field(default=None, max_length=2048)
    metadata_xml: str | None = None
    sso_only: bool = False


class SSOConfigUpdate(BaseModel):
    client_id: str | None = Field(default=None, max_length=512)
    client_secret: str | None = Field(default=None, max_length=512)
    discovery_url: str | None = Field(default=None, max_length=2048)
    metadata_url: str | None = Field(default=None, max_length=2048)
    metadata_xml: str | None = None
    sso_only: bool | None = None
    active: bool | None = None


class SSOConfigResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    organization_id: uuid.UUID
    sso_type: SSOType
    client_id: str | None
    discovery_url: str | None
    metadata_url: str | None
    keycloak_alias: str | None
    sso_only: bool
    active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Tenant membership schemas
# ---------------------------------------------------------------------------


class OrgTenantAdd(BaseModel):
    tenant_id: str = Field(..., description="Tenant UUID to add to this organization")


class OrgTenantResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    organization_id: uuid.UUID
    tenant_id: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Billing aggregation summary
# ---------------------------------------------------------------------------


class BillingSummaryResponse(BaseModel):
    organization_id: uuid.UUID
    organization_slug: str
    plan: OrgPlan
    tenant_count: int
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
