"""Pydantic schemas for the /access-requests API.

Kept separate from the SQLAlchemy model so we can validate user-supplied
data (anonymous POST!) without accidentally exposing audit fields like
`submitter_ip`, `reviewed_by`, `review_notes`.
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.access_request import AccessRequestStatus

# Honeypot: this field must be EMPTY. Bots fill every form field; humans
# can't see it (the UI hides it via CSS). Non-empty value → 400.
HONEYPOT_FIELD = "website"

# Reserved for clearly-disposable / abuse-magnet email TLDs. Kept short
# and conservative — we are enterprise, not a consumer product.
_BLOCKLIST_SUBSTRINGS = (
    "mailinator.com",
    "tempmail",
    "10minutemail",
    "guerrillamail",
)


class AccessRequestCreate(BaseModel):
    """Public-facing form submission."""

    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    org_name: str = Field(..., min_length=2, max_length=255)
    message: str | None = Field(default=None, max_length=2000)
    # Honeypot — bots fill it, humans don't (hidden in UI).
    website: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def _no_disposable(cls, v: str) -> str:
        lower = v.lower()
        for needle in _BLOCKLIST_SUBSTRINGS:
            if needle in lower:
                raise ValueError("please use a work email address")
        return v

    @field_validator("name", "org_name")
    @classmethod
    def _no_control_chars(cls, v: str) -> str:
        if re.search(r"[\x00-\x1f\x7f]", v):
            raise ValueError("invalid characters")
        return v.strip()


class AccessRequestResponse(BaseModel):
    """Response shape for platform-admin list/detail views."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    email: str
    org_name: str
    message: str | None
    status: AccessRequestStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_notes: str | None
    created_at: datetime
    updated_at: datetime


class AccessRequestReview(BaseModel):
    """Platform-admin approve/reject action."""

    status: AccessRequestStatus = Field(..., description="approved or rejected")
    review_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def _only_terminal_states(cls, v: AccessRequestStatus) -> AccessRequestStatus:
        if v == AccessRequestStatus.PENDING:
            raise ValueError("review must set status to approved or rejected")
        return v
