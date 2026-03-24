import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TenantCreate(BaseModel):
    slug: str = Field(..., min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    name: str = Field(..., min_length=1, max_length=255)
    cpu_limit: str = Field(default="16")
    memory_limit: str = Field(default="32Gi")
    storage_limit: str = Field(default="100Gi")

    @field_validator("slug")
    @classmethod
    def slug_no_reserved(cls, v: str) -> str:
        reserved = {"default", "kube-system", "kube-public", "kube-node-lease", "haven-system"}
        if v in reserved:
            raise ValueError(f"Slug '{v}' is reserved")
        return v


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    cpu_limit: str | None = None
    memory_limit: str | None = None
    storage_limit: str | None = None
    active: bool | None = None


class TenantResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    slug: str
    name: str
    namespace: str
    keycloak_realm: str
    cpu_limit: str
    memory_limit: str
    storage_limit: str
    active: bool
    created_at: datetime
    updated_at: datetime
