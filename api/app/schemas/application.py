import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ApplicationCreate(BaseModel):
    slug: str | None = Field(default=None, min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    name: str = Field(..., min_length=1, max_length=255)

    @model_validator(mode="after")
    def _set_slug_from_name(self) -> "ApplicationCreate":
        if self.slug is None:
            slug = re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")
            slug = slug[:63]
            if len(slug) < 3:
                slug = slug.ljust(3, "0")
            self.slug = slug
        return self
    repo_url: str = Field(..., max_length=2048)
    branch: str = Field(default="main", max_length=255)
    env_vars: dict[str, str] = Field(default_factory=dict)
    replicas: int = Field(default=1, ge=1, le=20)
    port: int = Field(default=8000, ge=1, le=65535)


class ApplicationUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    repo_url: str | None = Field(default=None, max_length=2048)
    branch: str | None = Field(default=None, max_length=255)
    env_vars: dict[str, str] | None = None
    replicas: int | None = Field(default=None, ge=1, le=20)
    port: int | None = Field(default=None, ge=1, le=65535)


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
    port: int
    webhook_token: str
    created_at: datetime
    updated_at: datetime
