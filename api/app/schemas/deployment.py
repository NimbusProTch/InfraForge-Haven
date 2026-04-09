import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.deployment import DeploymentStatus


class DeploymentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    application_id: uuid.UUID
    commit_sha: str
    status: DeploymentStatus
    build_job_name: str | None
    image_tag: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


# H3b (P2.2): BuildJobResponse removed alongside the deleted BuildJob model.
# It was dead code with zero callers — pipeline reads K8s Jobs directly.
