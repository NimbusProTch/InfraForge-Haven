import logging

import yaml
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.deps import CurrentUser, DBSession, GitQueueDep, K8sDep
from app.models.application import Application
from app.models.managed_service import ManagedService, ServiceStatus, ServiceType
from app.models.tenant import Tenant
from app.schemas.application import ApplicationCreate, ApplicationResponse, ApplicationUpdate
from app.services.deploy_service import DeployService
from app.services.git_queue_service import GitOperation, GitQueueService
from app.services.gitops_scaffold import gitops_scaffold
from app.services.helm_values_builder import render_app_values

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/apps", tags=["applications"])


async def _enqueue_app_values_update(
    queue: GitQueueService,
    tenant_slug: str,
    app: Application,
    reason: str,
) -> None:
    """Enqueue a values.yaml UPDATE_FILE job for an application."""
    try:
        values = render_app_values(app, tenant_slug)
        content = yaml.dump(values, default_flow_style=False, sort_keys=False)
        await queue.enqueue(
            GitOperation.UPDATE_FILE,
            {
                "tenant_slug": tenant_slug,
                "app_slug": app.slug,
                "values": values,
                "repo": settings.gitea_gitops_repo,
                "path": f"tenants/{tenant_slug}/{app.slug}/values.yaml",
                "commit_message": f"[haven] update {tenant_slug}/{app.slug} — {reason}",
                "author": "Haven Platform <haven@haven.dev>",
                "content": content,
            },
        )
        logger.info("Enqueued gitops update for %s/%s (%s)", tenant_slug, app.slug, reason)
    except Exception:
        logger.exception("Failed to enqueue gitops update for %s/%s", tenant_slug, app.slug)


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
        select(Application).where(Application.tenant_id == tenant.id).order_by(Application.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    tenant_slug: str, body: ApplicationCreate, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> Application:
    tenant = await _get_tenant_or_404(tenant_slug, db)

    # Check slug uniqueness within tenant
    existing = await db.execute(
        select(Application).where(Application.tenant_id == tenant.id, Application.slug == body.slug)
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
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail=f"Application '{body.slug}' already exists in tenant '{tenant_slug}'"
        )
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
        select(Application).where(Application.tenant_id == tenant.id, Application.slug == app_slug)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/{app_slug}", response_model=ApplicationResponse)
async def update_application(
    tenant_slug: str,
    app_slug: str,
    body: ApplicationUpdate,
    db: DBSession,
    current_user: CurrentUser,
    queue: GitQueueDep,
) -> Application:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(Application).where(Application.tenant_id == tenant.id, Application.slug == app_slug)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    updated_fields = body.model_dump(exclude_none=True)
    for field, value in updated_fields.items():
        setattr(app, field, value)

    await db.commit()
    await db.refresh(app)

    # Enqueue values.yaml update for any config change.
    # Skip if no image_tag yet (first build hasn't run) — prevents wiping existing deployment.
    if queue is not None and updated_fields and app.image_tag:
        gitops_fields = {
            "env_vars",
            "replicas",
            "port",
            "resources",
            "custom_domain",
            "health_check_path",
            "resource_cpu_request",
            "resource_cpu_limit",
            "resource_memory_request",
            "resource_memory_limit",
            "min_replicas",
            "max_replicas",
            "cpu_threshold",
        }
        if updated_fields.keys() & gitops_fields:
            await _enqueue_app_values_update(queue, tenant_slug, app, "config update")

    return app


class _SecretVarsBody(BaseModel):
    """Request body for PUT /secrets — key-value pairs for sensitive env vars."""

    secrets: dict[str, str]


@router.put("/{app_slug}/secrets", response_model=dict)
async def upsert_secrets(
    tenant_slug: str,
    app_slug: str,
    body: _SecretVarsBody,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> dict:
    """Write sensitive env vars to Vault (or K8s Secret fallback).

    These are injected into the pod via envFrom.secretRef and never stored in GitOps.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    from app.services.secret_service import SecretService

    svc = SecretService(k8s)
    await svc.upsert_sensitive_vars(
        namespace=tenant.namespace,
        app_slug=app.slug,
        tenant_slug=tenant.slug,
        data=body.secrets,
    )
    return {"status": "ok", "keys": list(body.secrets.keys()), "vault": svc.uses_vault()}


@router.get("/{app_slug}/secrets", response_model=dict)
async def list_secret_keys(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> dict:
    """List sensitive env var keys (values never returned via API)."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    from app.services.secret_service import SecretService

    svc = SecretService(k8s)
    if svc.uses_vault():
        from app.services.vault_service import vault_service

        keys = await vault_service.list_keys(tenant.slug, app.slug)
    else:
        keys = svc.list_secret_keys(tenant.namespace, app.slug)
    return {"keys": keys, "vault": svc.uses_vault()}


@router.delete("/{app_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    tenant_slug: str, app_slug: str, db: DBSession, k8s: K8sDep, current_user: CurrentUser
) -> None:
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(Application).where(Application.tenant_id == tenant.id, Application.slug == app_slug)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    # GitOps scaffold: remove app directory from haven-gitops (non-blocking)
    await gitops_scaffold.delete_app(tenant_slug=tenant_slug, app_slug=app_slug)

    # Undeploy K8s resources (Deployment, Service, HTTPRoute, HPA)
    namespace = f"tenant-{tenant_slug}"
    if k8s is not None and k8s.is_available():
        try:
            deploy_svc = DeployService(k8s)
            await deploy_svc.undeploy(namespace=namespace, app_slug=app_slug)
            logger.info("K8s resources cleaned up for %s/%s", namespace, app_slug)
        except Exception:
            logger.exception("Failed to clean up K8s resources for %s/%s", namespace, app_slug)

    await db.delete(app)
    await db.commit()


# ---------------------------------------------------------------------------
# Managed service connections
# ---------------------------------------------------------------------------


def _database_url_key(service_type: ServiceType) -> str | None:
    """Return the conventional env var name for a database URL, by type."""
    return {
        ServiceType.POSTGRES: "DATABASE_URL",
        ServiceType.MYSQL: "MYSQL_URL",
        ServiceType.MONGODB: "MONGODB_URL",
    }.get(service_type)


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
    queue: GitQueueDep,
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
        raise HTTPException(status_code=409, detail=f"Service '{svc.name}' is not ready (status: {svc.status})")
    if not svc.secret_name or not svc.service_namespace:
        raise HTTPException(status_code=409, detail="Service has no credentials yet")
    if not svc.credentials_provisioned:
        raise HTTPException(status_code=409, detail="Service credentials are being provisioned — try again shortly")

    existing: list[dict] = list(app.env_from_secrets or [])
    if not any(e.get("service_name") == svc.name for e in existing):
        # Build DATABASE_URL template from service type + connection info
        db_url_key = _database_url_key(svc.service_type)
        existing.append(
            {
                "service_name": svc.name,
                "secret_name": svc.secret_name,
                "namespace": svc.service_namespace,
                "connection_hint": svc.connection_hint,
                "database_url_key": db_url_key,
            }
        )
        # Also inject DATABASE_URL (and type-specific alias) into app env_vars
        if svc.connection_hint and db_url_key:
            env_vars = dict(app.env_vars or {})
            env_vars[db_url_key] = svc.connection_hint
            # Always set generic DATABASE_URL as well
            if db_url_key != "DATABASE_URL":
                env_vars["DATABASE_URL"] = svc.connection_hint
            app.env_vars = env_vars
        app.env_from_secrets = existing
        await db.commit()
        await db.refresh(app)

    if queue is not None and app.image_tag:
        await _enqueue_app_values_update(queue, tenant_slug, app, f"connect service {svc.name}")

    return app


@router.delete("/{app_slug}/connect-service/{service_name}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_service(
    tenant_slug: str,
    app_slug: str,
    service_name: str,
    db: DBSession,
    current_user: CurrentUser,
    queue: GitQueueDep,
) -> None:
    """Remove a managed service secret from an app's envFrom list."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    existing: list[dict] = list(app.env_from_secrets or [])
    # Find the entry being removed so we can clean up injected env_vars
    removed = [e for e in existing if e.get("service_name") == service_name]
    updated = [e for e in existing if e.get("service_name") != service_name]
    app.env_from_secrets = updated or None

    # Remove env_vars that were injected by connect-service
    if removed and app.env_vars:
        env_vars = dict(app.env_vars)
        for entry in removed:
            db_url_key = entry.get("database_url_key")
            if db_url_key and db_url_key in env_vars:
                del env_vars[db_url_key]
            # Also remove generic DATABASE_URL if it was added as alias
            if db_url_key and db_url_key != "DATABASE_URL" and "DATABASE_URL" in env_vars:
                del env_vars["DATABASE_URL"]
        app.env_vars = env_vars if env_vars else {}

    await db.commit()
    await db.refresh(app)

    if queue is not None and app.image_tag:
        await _enqueue_app_values_update(queue, tenant_slug, app, f"disconnect service {service_name}")
