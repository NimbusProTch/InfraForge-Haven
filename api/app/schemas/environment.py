import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.environment import EnvironmentStatus, EnvironmentType


class EnvironmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    env_type: EnvironmentType = EnvironmentType.staging
    branch: str = Field(default="main", max_length=255)
    env_vars: dict[str, str] = Field(default_factory=dict)
    replicas: int | None = Field(default=None, ge=1, le=20)


class EnvironmentUpdate(BaseModel):
    branch: str | None = Field(default=None, max_length=255)
    env_vars: dict[str, str] | None = None
    replicas: int | None = Field(default=None, ge=1, le=20)
    status: EnvironmentStatus | None = None


class EnvironmentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    application_id: uuid.UUID
    name: str
    env_type: EnvironmentType
    branch: str
    status: EnvironmentStatus
    pr_number: int | None
    env_vars: dict
    replicas: int | None
    domain: str | None
    last_image_tag: str | None
    created_at: datetime
    updated_at: datetime
