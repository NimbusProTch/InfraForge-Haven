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

    # Monorepo support
    dockerfile_path: str | None = Field(default=None, max_length=512)
    build_context: str | None = Field(default=None, max_length=512)
    use_dockerfile: bool = Field(default=False)

    # Production hardening
    custom_domain: str | None = Field(default=None, max_length=255)
    health_check_path: str | None = Field(default=None, max_length=512)
    resource_cpu_request: str = Field(default="50m", max_length=32)
    resource_cpu_limit: str = Field(default="500m", max_length=32)
    resource_memory_request: str = Field(default="64Mi", max_length=32)
    resource_memory_limit: str = Field(default="512Mi", max_length=32)
    min_replicas: int = Field(default=1, ge=1, le=50)
    max_replicas: int = Field(default=5, ge=1, le=100)
    cpu_threshold: int = Field(default=70, ge=10, le=100)
    auto_deploy: bool = Field(default=True)


class ApplicationUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    repo_url: str | None = Field(default=None, max_length=2048)
    branch: str | None = Field(default=None, max_length=255)
    env_vars: dict[str, str] | None = None
    replicas: int | None = Field(default=None, ge=1, le=20)
    port: int | None = Field(default=None, ge=1, le=65535)

    # Monorepo support
    dockerfile_path: str | None = None
    build_context: str | None = None
    use_dockerfile: bool | None = None

    # Production hardening
    custom_domain: str | None = None
    health_check_path: str | None = None
    resource_cpu_request: str | None = Field(default=None, max_length=32)
    resource_cpu_limit: str | None = Field(default=None, max_length=32)
    resource_memory_request: str | None = Field(default=None, max_length=32)
    resource_memory_limit: str | None = Field(default=None, max_length=32)
    min_replicas: int | None = Field(default=None, ge=1, le=50)
    max_replicas: int | None = Field(default=None, ge=1, le=100)
    cpu_threshold: int | None = Field(default=None, ge=10, le=100)
    auto_deploy: bool | None = None


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

    # Monorepo
    dockerfile_path: str | None = None
    build_context: str | None = None
    use_dockerfile: bool = False
    detected_deps: dict | None = None

    # Production hardening
    custom_domain: str | None = None
    health_check_path: str | None = None
    resource_cpu_request: str = "50m"
    resource_cpu_limit: str = "500m"
    resource_memory_request: str = "64Mi"
    resource_memory_limit: str = "512Mi"
    min_replicas: int = 1
    max_replicas: int = 5
    cpu_threshold: int = 70
    auto_deploy: bool = True

    created_at: datetime
    updated_at: datetime
