import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.domain import CertificateStatus


class DomainCreate(BaseModel):
    domain: str

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or len(v) > 255:
            raise ValueError("Domain must be 1-255 characters")
        # Basic domain format check (no protocol prefix)
        if "://" in v:
            raise ValueError("Domain must not include protocol (e.g. use 'example.com' not 'https://example.com')")
        # Must have at least one dot
        parts = v.split(".")
        if len(parts) < 2 or any(not p for p in parts):
            raise ValueError("Invalid domain format")
        return v


class DomainResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    domain: str
    verification_token: str
    verified_at: datetime | None
    certificate_status: CertificateStatus
    certificate_expires_at: datetime | None
    certificate_error: str | None
    created_at: datetime
    updated_at: datetime

    # Computed helper fields for the UI
    txt_record_name: str
    txt_record_value: str
    cname_instructions: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_instructions(cls, domain: object, lb_hostname: str) -> "DomainResponse":
        """Build response with DNS instructions computed from LB hostname."""
        from app.models.domain import DomainVerification

        d: DomainVerification = domain  # type: ignore[assignment]
        return cls(
            id=d.id,
            application_id=d.application_id,
            domain=d.domain,
            verification_token=d.verification_token,
            verified_at=d.verified_at,
            certificate_status=d.certificate_status,
            certificate_expires_at=d.certificate_expires_at,
            certificate_error=d.certificate_error,
            created_at=d.created_at,
            updated_at=d.updated_at,
            txt_record_name=f"_haven-verify.{d.domain}",
            txt_record_value=d.verification_token,
            cname_instructions=f"Add a CNAME record: {d.domain} → {lb_hostname}",
        )


class DomainVerifyResponse(BaseModel):
    verified: bool
    message: str
    certificate_status: CertificateStatus


class WildcardCertRequest(BaseModel):
    """Request to issue a wildcard certificate for *.apps.{platform_domain}."""
    platform_domain: str
    cloudflare_api_token: str | None = None
