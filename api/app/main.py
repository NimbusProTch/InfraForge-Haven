import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.k8s.client import k8s_client
from app.routers import (
    applications,
    audit,
    backup,
    billing,
    build_queue,
    canary,
    clusters,
    cronjobs,
    deployments,
    domains,
    environments,
    events,
    gdpr,
    gitea,
    gitea_repos,
    github,
    health,
    members,
    observability,
    organizations,
    pvcs,
    queue_status,
    services,
    tenants,
    webhooks,
)

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


async def _auto_connect_pending_services(db: object, svc: object, tenant: object) -> None:
    """Auto-connect a READY service to apps that requested it during creation.

    Scans all apps in the tenant for matching pending_services entries.
    When found, performs the same logic as connect-service endpoint:
    appends to env_from_secrets, injects DATABASE_URL, clears pending entry.
    """
    from sqlalchemy import select

    from app.models.application import Application
    from app.models.managed_service import ServiceType

    result = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant.id,
            Application.pending_services.isnot(None),
        )
    )
    apps = list(result.scalars().all())

    for app in apps:
        pending = list(app.pending_services or [])
        matched = [p for p in pending if p.get("service_name") == svc.name]
        if not matched:
            continue

        # Connect the service to the app
        existing_secrets: list[dict] = list(app.env_from_secrets or [])
        if any(e.get("service_name") == svc.name for e in existing_secrets):
            # Already connected, just remove from pending
            remaining = [p for p in pending if p.get("service_name") != svc.name]
            app.pending_services = remaining or None
            await db.commit()
            continue

        # Build connection entry (same as connect-service endpoint)
        db_url_key_map = {
            ServiceType.POSTGRES: "DATABASE_URL",
            ServiceType.MYSQL: "MYSQL_URL",
            ServiceType.MONGODB: "MONGODB_URL",
        }
        db_url_key = db_url_key_map.get(svc.service_type)

        existing_secrets.append(
            {
                "service_name": svc.name,
                "secret_name": svc.secret_name,
                "namespace": svc.service_namespace,
                "connection_hint": svc.connection_hint,
                "database_url_key": db_url_key,
            }
        )

        # Inject DATABASE_URL into env_vars
        if svc.connection_hint and db_url_key:
            env_vars = dict(app.env_vars or {})
            env_vars[db_url_key] = svc.connection_hint
            if db_url_key != "DATABASE_URL":
                env_vars["DATABASE_URL"] = svc.connection_hint
            app.env_vars = env_vars

        app.env_from_secrets = existing_secrets

        # Remove from pending
        remaining = [p for p in pending if p.get("service_name") != svc.name]
        app.pending_services = remaining or None

        await db.commit()
        logger.info(
            "Auto-connected service %s to app %s (pending_services remaining: %d)",
            svc.name,
            app.slug,
            len(remaining),
        )


async def _credential_provisioning_tick(session_factory: object) -> int:
    """Single tick of the credential provisioning loop. Returns count of services processed.

    Finds services that are either:
    1. PROVISIONING (need status sync from Everest/CRD)
    2. READY but credentials not yet provisioned (need custom user/db/secret)

    Each service is processed independently — one failure doesn't block others.
    """
    from datetime import datetime, timedelta

    from sqlalchemy import or_, select

    from app.models.managed_service import ManagedService, ServiceStatus
    from app.models.tenant import Tenant
    from app.services.managed_service import ManagedServiceProvisioner

    service_provision_timeout = timedelta(minutes=10)

    # Fetch service IDs in a read-only session
    async with session_factory() as db:
        result = await db.execute(
            select(ManagedService.id).where(
                or_(
                    ManagedService.status == ServiceStatus.PROVISIONING,
                    ManagedService.status == ServiceStatus.UPDATING,
                    (ManagedService.status == ServiceStatus.READY) & (ManagedService.credentials_provisioned == False),  # noqa: E712
                )
            )
        )
        service_ids = [row[0] for row in result.all()]

    if not service_ids:
        return 0

    # Process each service in its own session + transaction
    provisioner = ManagedServiceProvisioner(k8s_client)
    processed = 0
    now = datetime.now(UTC)
    for svc_id in service_ids:
        try:
            async with session_factory() as db:
                svc = await db.get(ManagedService, svc_id)
                if svc is None:
                    continue

                # Timeout: if stuck in PROVISIONING/UPDATING for too long → FAILED
                # Use updated_at for UPDATING (reflects when status changed), created_at for PROVISIONING
                if svc.status in (ServiceStatus.PROVISIONING, ServiceStatus.UPDATING):
                    ref_time = svc.updated_at if svc.status == ServiceStatus.UPDATING else svc.created_at
                    age = now - ref_time.replace(tzinfo=UTC) if ref_time.tzinfo is None else now - ref_time
                    if age > service_provision_timeout:
                        svc.status = ServiceStatus.FAILED
                        svc.error_message = f"Service timed out after {int(age.total_seconds() // 60)} minutes"
                        logger.warning("Service %s timed out (age: %s)", svc.name, age)
                        await db.commit()
                        processed += 1
                        continue

                tenant = await db.get(Tenant, svc.tenant_id)
                if tenant and tenant.namespace:
                    await provisioner.sync_details(svc, tenant_namespace=tenant.namespace)
                await db.commit()

                # Auto-connect: if service just became READY with credentials,
                # check if any app has it in pending_services and auto-connect
                if svc.status == ServiceStatus.READY and svc.credentials_provisioned:
                    await _auto_connect_pending_services(db, svc, tenant)

                processed += 1
        except Exception:
            logger.exception("Credential provisioning failed for service %s", svc_id)

    return processed


async def _credential_provisioning_loop() -> None:
    """Background loop: provision custom credentials for READY Everest databases.

    Runs every 15 seconds. Finds services that are READY but haven't had
    custom credentials provisioned yet, and creates custom user/db/secret.
    This removes the dependency on a UI GET request to trigger provisioning.
    """
    from app.deps import get_session_factory

    session_factory = get_session_factory()

    while True:
        await asyncio.sleep(15)
        try:
            count = await _credential_provisioning_tick(session_factory)
            if count:
                logger.info("Background credential loop: processed %d services", count)
        except Exception:
            logger.exception("Credential provisioning loop error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Haven Platform API")
    await k8s_client.initialize()
    task = asyncio.create_task(_credential_provisioning_loop())
    yield
    task.cancel()
    logger.info("Shutting down Haven Platform API")
    await k8s_client.close()


app = FastAPI(
    title="Haven Platform API",
    description="Haven-Compliant Self-Service DevOps Platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging with correlation ID
from app.middleware.request_logging import RequestLoggingMiddleware  # noqa: E402

app.add_middleware(RequestLoggingMiddleware)


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


def _cors_headers(request: Request) -> dict[str, str]:
    """Return CORS headers for error responses so browsers can read the error."""
    origin = request.headers.get("origin", "")
    if not origin:
        return {}
    allowed = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if origin in allowed or "*" in allowed:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
        headers=_cors_headers(request),
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health.router)
app.include_router(tenants.router, prefix=settings.api_prefix)
app.include_router(applications.router, prefix=settings.api_prefix)
app.include_router(deployments.router, prefix=settings.api_prefix)
app.include_router(services.router, prefix=settings.api_prefix)
app.include_router(webhooks.router, prefix=settings.api_prefix)
app.include_router(github.router, prefix=settings.api_prefix)
app.include_router(observability.router, prefix=settings.api_prefix)
app.include_router(members.router, prefix=settings.api_prefix)
app.include_router(environments.router, prefix=settings.api_prefix)
app.include_router(domains.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(billing.router, prefix=settings.api_prefix)
app.include_router(gdpr.router, prefix=settings.api_prefix)
app.include_router(organizations.router, prefix=settings.api_prefix)
app.include_router(backup.router, prefix=settings.api_prefix)
app.include_router(canary.router, prefix=settings.api_prefix)
app.include_router(cronjobs.router, prefix=settings.api_prefix)
app.include_router(pvcs.router, prefix=settings.api_prefix)
app.include_router(clusters.router, prefix=settings.api_prefix)
app.include_router(gitea.router, prefix=settings.api_prefix)
app.include_router(gitea_repos.router, prefix=settings.api_prefix)
app.include_router(queue_status.router, prefix=settings.api_prefix)
app.include_router(build_queue.router, prefix=settings.api_prefix)
app.include_router(events.router, prefix=settings.api_prefix)
