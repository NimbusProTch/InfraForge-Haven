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
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ConnectedAppSummary(BaseModel):
    slug: str
    name: str


class ServiceRuntimeDetails(BaseModel):
    engine_version: str | None = None
    replicas: int | None = None
    ready_replicas: int | None = None
    storage: str | None = None
    cpu: str | None = None
    memory: str | None = None
    hostname: str | None = None
    port: int | None = None


class ManagedServiceDetailResponse(ManagedServiceResponse):
    """Enriched response for single service detail — includes live Everest data."""

    runtime: ServiceRuntimeDetails | None = None
    connected_apps: list[ConnectedAppSummary] = []


class ManagedServiceUpdate(BaseModel):
    """Update database resources. Only provided fields are changed."""

    replicas: int | None = Field(None, ge=1, le=7)
    storage: str | None = Field(None, pattern=r"^\d+Gi$")
    cpu: str | None = Field(None, pattern=r"^\d+m?$")
    memory: str | None = Field(None, pattern=r"^\d+(Mi|Gi)$")


class ServiceCredentials(BaseModel):
    service_name: str
    secret_name: str
    connection_hint: str | None
    credentials: dict[str, str]
