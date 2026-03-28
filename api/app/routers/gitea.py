"""Internal Gitea health and status endpoints."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.gitea_client import gitea_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/gitea", tags=["internal"])


class GiteaHealth(BaseModel):
    healthy: bool
    gitea_url: str
    configured: bool


@router.get("/health", response_model=GiteaHealth)
async def gitea_health() -> GiteaHealth:
    """Check whether the Gitea service is reachable and configured."""
    configured = bool(gitea_client._base_url and gitea_client._token)
    healthy = await gitea_client.health() if configured else False
    return GiteaHealth(
        healthy=healthy,
        gitea_url=gitea_client._base_url,
        configured=configured,
    )
