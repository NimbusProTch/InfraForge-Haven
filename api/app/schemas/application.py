import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    slug: str = Field(..., min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    name: str = Field(..., min_length=1, max_length=255)
    repo_url: str = Field(..., max_length=2048)
    branch: str = Field(default="main", max_length=255)
    env_vars: dict[str, str] = Field(default_factory=dict)
    replicas: int = Field(default=1, ge=1, le=20)


class ApplicationUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    branch: str | None = Field(default=None, max_length=255)
    env_vars: dict[str, str] | None = None
    replicas: int | None = Field(default=None, ge=1, le=20)


class ApplicationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    name: str
    repo_url: str
    branch: str
    env_vars: dict
    image_tag: str | None
    replicas: int
    created_at: datetime
    updated_at: datetime
