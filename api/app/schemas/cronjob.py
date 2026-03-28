import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CronJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    schedule: str = Field(..., min_length=1, max_length=100, description="Cron expression: '0 * * * *'")
    command: list[str] | None = Field(default=None)
    cpu_request: str = Field(default="50m", max_length=32)
    cpu_limit: str = Field(default="500m", max_length=32)
    memory_request: str = Field(default="64Mi", max_length=32)
    memory_limit: str = Field(default="256Mi", max_length=32)
    concurrency_policy: str = Field(default="Forbid", pattern=r"^(Allow|Forbid|Replace)$")
    successful_jobs_history: int = Field(default=3, ge=0, le=10)
    failed_jobs_history: int = Field(default=1, ge=0, le=10)
    starting_deadline_seconds: int | None = Field(default=None, ge=10)
    suspended: bool = Field(default=False)
    env_vars: dict[str, str] | None = Field(default=None)
    description: str | None = Field(default=None, max_length=1000)


class CronJobUpdate(BaseModel):
    schedule: str | None = Field(default=None, max_length=100)
    command: list[str] | None = None
    cpu_request: str | None = Field(default=None, max_length=32)
    cpu_limit: str | None = Field(default=None, max_length=32)
    memory_request: str | None = Field(default=None, max_length=32)
    memory_limit: str | None = Field(default=None, max_length=32)
    concurrency_policy: str | None = Field(default=None, pattern=r"^(Allow|Forbid|Replace)$")
    suspended: bool | None = None
    env_vars: dict[str, str] | None = None
    description: str | None = None


class CronJobResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    application_id: uuid.UUID
    name: str
    schedule: str
    command: list[str] | None
    cpu_request: str
    cpu_limit: str
    memory_request: str
    memory_limit: str
    concurrency_policy: str
    successful_jobs_history: int
    failed_jobs_history: int
    starting_deadline_seconds: int | None
    suspended: bool
    k8s_name: str | None
    last_schedule: str | None
    last_status: str | None
    env_vars: dict | None
    description: str | None
    created_at: datetime
    updated_at: datetime
