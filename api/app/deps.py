from collections.abc import AsyncGenerator
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.jwt import verify_token
from app.config import settings
from app.k8s.client import K8sClient, k8s_client
from app.services.argocd_service import ArgoCDService
from app.services.git_queue_service import GitQueueService
from app.services.gitops_service import GitOpsService

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_engine = create_async_engine(settings.database_url, echo=settings.debug, pool_pre_ping=True)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _SessionLocal() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory for use in background tasks."""
    return _SessionLocal


DBSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Kubernetes
# ---------------------------------------------------------------------------
def get_k8s() -> K8sClient:
    return k8s_client


K8sDep = Annotated[K8sClient, Depends(get_k8s)]


# ---------------------------------------------------------------------------
# GitOps
# ---------------------------------------------------------------------------
_gitops_service = GitOpsService()
_argocd_service = ArgoCDService()


def get_gitops() -> GitOpsService:
    return _gitops_service


def get_argocd() -> ArgoCDService:
    return _argocd_service


GitOpsDep = Annotated[GitOpsService, Depends(get_gitops)]
ArgoCDDep = Annotated[ArgoCDService, Depends(get_argocd)]

# ---------------------------------------------------------------------------
# Git Queue (Redis-backed, optional)
# ---------------------------------------------------------------------------
_redis_client: aioredis.Redis | None = None
_git_queue_service: GitQueueService | None = None


def get_git_queue() -> GitQueueService | None:
    """Return a GitQueueService backed by Redis, or None if not configured."""
    if not settings.redis_url:
        return None
    global _redis_client, _git_queue_service  # noqa: PLW0603
    if _git_queue_service is None:
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=False)
        _git_queue_service = GitQueueService(_redis_client)
    return _git_queue_service


GitQueueDep = Annotated[GitQueueService | None, Depends(get_git_queue)]

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
CurrentUser = Annotated[dict[str, Any], Depends(verify_token)]
