"""Internal Gitea health and status endpoints."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.jwt import verify_token
from app.services.gitea_client import gitea_client

logger = logging.getLogger(__name__)

# H0-14: every endpoint in this router requires a valid JWT.
# Pre-fix this endpoint was unauthenticated and exposed the internal
# Gitea base URL — an information disclosure on infrastructure topology.
router = APIRouter(prefix="/internal/gitea", tags=["internal"], dependencies=[Depends(verify_token)])


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
