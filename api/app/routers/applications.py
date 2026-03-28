import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import CurrentUser, DBSession, K8sDep
from app.models.application import Application
from app.models.managed_service import ManagedService, ServiceStatus
from app.models.tenant import Tenant
from app.schemas.application import ApplicationCreate, ApplicationResponse, ApplicationUpdate
from app.services.gitops_scaffold import gitops_scaffold

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/apps", tags=["applications"])


async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.get("", response_model=list[ApplicationResponse])
async def list_applications(tenant_slug: str, db: DBSession, current_user: CurrentUser) -> list[Application]:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(Application)
        .where(Application.tenant_id == tenant.id)
        .order_by(Application.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    tenant_slug: str, body: ApplicationCreate, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> Application:
    tenant = await _get_tenant_or_404(tenant_slug, db)

    # Check slug uniqueness within tenant
    existing = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant.id, Application.slug == body.slug
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Application '{body.slug}' already exists")

    app = Application(
        tenant_id=tenant.id,
        slug=body.slug,
        name=body.name,
        repo_url=body.repo_url,
        branch=body.branch,
        env_vars=body.env_vars,
        replicas=body.replicas,
        port=body.port,
        app_type=body.app_type,
        canary_enabled=body.canary_enabled,
        canary_weight=body.canary_weight,
        volumes=body.volumes,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    # GitOps scaffold: create app values.yaml in haven-gitops (non-blocking)
    await gitops_scaffold.scaffold_app(
        tenant_slug=tenant_slug,
        app_slug=body.slug,
        port=body.port or 8000,
        replicas=body.replicas or 1,
        env_vars=dict(body.env_vars) if body.env_vars else {},
    )

    return app


@router.get("/{app_slug}", response_model=ApplicationResponse)
async def get_application(tenant_slug: str, app_slug: str, db: DBSession, current_user: CurrentUser) -> Application:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant.id, Application.slug == app_slug
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/{app_slug}", response_model=ApplicationResponse)
async def update_application(
    tenant_slug: str, app_slug: str, body: ApplicationUpdate, db: DBSession, current_user: CurrentUser
) -> Application:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant.id, Application.slug == app_slug
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(app, field, value)

    await db.commit()
    await db.refresh(app)
    return app


@router.delete("/{app_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    tenant_slug: str, app_slug: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> None:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant.id, Application.slug == app_slug
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    # GitOps scaffold: remove app directory from haven-gitops (non-blocking)
    await gitops_scaffold.delete_app(tenant_slug=tenant_slug, app_slug=app_slug)

    # TODO (Sprint 3): undeploy from K8s before deleting from DB
    await db.delete(app)
    await db.commit()


# ---------------------------------------------------------------------------
# Managed service connections
# ---------------------------------------------------------------------------


class _ConnectServiceBody(BaseModel):
    service_name: str


async def _get_app_or_404(tenant_id: object, app_slug: str, db: DBSession) -> Application:
    result = await db.execute(
        select(Application).where(Application.tenant_id == tenant_id, Application.slug == app_slug)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.post("/{app_slug}/connect-service", response_model=ApplicationResponse)
async def connect_service(
    tenant_slug: str,
    app_slug: str,
    body: _ConnectServiceBody,
    db: DBSession,
    current_user: CurrentUser,
) -> Application:
    """Attach a managed service secret to an app's envFrom list."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    result = await db.execute(
        select(ManagedService).where(
            ManagedService.tenant_id == tenant.id,
            ManagedService.name == body.service_name,
        )
    )
    svc = result.scalar_one_or_none()
    if svc is None:
        raise HTTPException(status_code=404, detail="Service not found")
    if svc.status != ServiceStatus.READY:
        raise HTTPException(
            status_code=409, detail=f"Service '{svc.name}' is not ready (status: {svc.status})"
        )
    if not svc.secret_name or not svc.service_namespace:
        raise HTTPException(status_code=409, detail="Service has no credentials yet")

    existing: list[dict] = list(app.env_from_secrets or [])
    if not any(e.get("service_name") == svc.name for e in existing):
        existing.append(
            {
                "service_name": svc.name,
                "secret_name": svc.secret_name,
                "namespace": svc.service_namespace,
            }
        )
        app.env_from_secrets = existing
        await db.commit()
        await db.refresh(app)
    return app


@router.delete("/{app_slug}/connect-service/{service_name}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_service(
    tenant_slug: str,
    app_slug: str,
    service_name: str,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Remove a managed service secret from an app's envFrom list."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    existing: list[dict] = list(app.env_from_secrets or [])
    updated = [e for e in existing if e.get("service_name") != service_name]
    app.env_from_secrets = updated or None
    await db.commit()
