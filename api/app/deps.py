from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.jwt import verify_token
from app.config import settings
from app.k8s.client import K8sClient, k8s_client

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
# Auth
# ---------------------------------------------------------------------------
CurrentUser = Annotated[dict[str, Any], Depends(verify_token)]
