import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.tenant_member import MemberRole


class TenantMemberInvite(BaseModel):
    email: str = Field(..., max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    role: MemberRole = MemberRole.member
    # Keycloak user_id is resolved server-side; optionally pre-supply it
    user_id: str | None = None


class TenantMemberUpdate(BaseModel):
    role: MemberRole


class TenantMemberResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: str
    email: str
    display_name: str | None
    role: MemberRole
    created_at: datetime
    updated_at: datetime
