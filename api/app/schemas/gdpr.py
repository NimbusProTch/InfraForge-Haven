import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.user_consent import ConsentType


# ---------------------------------------------------------------------------
# Consent schemas
# ---------------------------------------------------------------------------


class ConsentGrant(BaseModel):
    consent_type: ConsentType
    ip_address: str | None = None
    user_agent: str | None = None
    context: str | None = None


class ConsentRevoke(BaseModel):
    consent_type: ConsentType


class ConsentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: str
    consent_type: ConsentType
    granted: bool
    ip_address: str | None
    context: str | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Data retention schemas
# ---------------------------------------------------------------------------


class RetentionPolicyUpdate(BaseModel):
    audit_log_days: int | None = Field(default=None, ge=0)
    deployment_log_days: int | None = Field(default=None, ge=0)
    build_log_days: int | None = Field(default=None, ge=0)
    usage_record_days: int | None = Field(default=None, ge=0)
    inactive_app_days: int | None = Field(default=None, ge=0)
    notes: str | None = None


class RetentionPolicyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: str
    audit_log_days: int
    deployment_log_days: int
    build_log_days: int
    usage_record_days: int
    inactive_app_days: int
    policy_version: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Data export / erasure schemas
# ---------------------------------------------------------------------------


class DataExportResponse(BaseModel):
    """GDPR Art. 20 — Data portability export."""

    exported_at: datetime
    tenant_slug: str
    requesting_user_id: str
    applications: list[dict]
    deployments: list[dict]
    consents: list[dict]
    members: list[dict]


class ErasureRequest(BaseModel):
    """GDPR Art. 17 — Right to erasure request.

    Requires explicit confirmation string to prevent accidental deletion.
    """

    confirm: str = Field(..., description="Must equal 'ERASE MY DATA' to confirm")


class ErasureResponse(BaseModel):
    erased_at: datetime
    tenant_slug: str
    requesting_user_id: str
    records_deleted: dict[str, int]
