import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from app.config import settings
from app.k8s.client import k8s_client
from app.routers import applications, health, tenants, webhooks

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Haven Platform API")
    await k8s_client.initialize()
    yield
    logger.info("Shutting down Haven Platform API")
    await k8s_client.close()


app = FastAPI(
    title="Haven Platform API",
    description="Haven-Compliant Self-Service DevOps Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(tenants.router, prefix=settings.api_prefix)
app.include_router(applications.router, prefix=settings.api_prefix)
app.include_router(webhooks.router, prefix=settings.api_prefix)
