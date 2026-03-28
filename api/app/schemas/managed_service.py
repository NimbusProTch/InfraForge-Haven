import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.managed_service import ServiceStatus, ServiceTier, ServiceType


class ManagedServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    service_type: ServiceType
    tier: ServiceTier = ServiceTier.DEV

    @field_validator("name")
    @classmethod
    def name_not_reserved(cls, v: str) -> str:
        reserved = {"default", "admin", "system"}
        if v in reserved:
            raise ValueError(f"Name '{v}' is reserved")
        return v


class ManagedServiceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    service_type: ServiceType
    tier: ServiceTier
    status: ServiceStatus
    secret_name: str | None
    connection_hint: str | None
    created_at: datetime
    updated_at: datetime


class ServiceCredentials(BaseModel):
    service_name: str
    secret_name: str
    connection_hint: str | None
    credentials: dict[str, str]
