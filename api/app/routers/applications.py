"""Application CRUD + secrets + service-connection endpoints.

H3e (P2.5 / P19 batch 3): migrated to canonical `TenantMembership`
dependency from `app/deps.py`. The local `_get_tenant_or_404` helper has
been removed. Endpoints that write audit log entries still take
`CurrentUser` so they can stamp `user_id` onto the audit row.
"""

import logging
from datetime import UTC

import yaml
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.deps import CurrentUser, DBSession, GitQueueDep, K8sDep, TenantMembership
from app.models.application import Application
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType
from app.schemas.application import ApplicationCreate, ApplicationResponse, ApplicationUpdate
from app.services.audit_service import audit
from app.services.deploy_service import DeployService
from app.services.git_queue_service import GitOperation, GitQueueService
from app.services.gitops_scaffold import gitops_scaffold
from app.services.helm_values_builder import render_app_values
from app.services.managed_service import ManagedServiceProvisioner

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
                "author": "iyziops <noreply@iyziops.com>",
                "content": content,
            },
        )
        logger.info("Enqueued gitops update for %s/%s (%s)", tenant_slug, app.slug, reason)
    except Exception:
        logger.exception("Failed to enqueue gitops update for %s/%s", tenant_slug, app.slug)


@router.get("", response_model=list[ApplicationResponse])
async def list_applications(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    db: DBSession,
    tenant: TenantMembership,
) -> list[Application]:
    result = await db.execute(
        select(Application).where(Application.tenant_id == tenant.id).order_by(Application.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    tenant_slug: str,
    body: ApplicationCreate,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
    current_user: CurrentUser,
) -> Application:
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
        dockerfile_path=body.dockerfile_path,
        build_context=body.build_context,
        use_dockerfile=body.use_dockerfile,
        health_check_path=body.health_check_path,
        custom_domain=body.custom_domain,
        auto_deploy=body.auto_deploy,
        resource_cpu_request=body.resource_cpu_request,
        resource_cpu_limit=body.resource_cpu_limit,
        resource_memory_request=body.resource_memory_request,
        resource_memory_limit=body.resource_memory_limit,
        min_replicas=body.min_replicas,
        max_replicas=body.max_replicas,
        cpu_threshold=body.cpu_threshold,
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

    # Auto-create requested services alongside the app
    if body.requested_services:
        pending: list[dict] = []
        for req in body.requested_services:
            svc_name = req.name or f"{body.slug}-{req.service_type}"
            svc_type = ServiceType(req.service_type)
            svc_tier = ServiceTier(req.tier)

            # Skip if service already exists
            existing_svc = await db.execute(
                select(ManagedService).where(
                    ManagedService.tenant_id == tenant.id,
                    ManagedService.name == svc_name,
                )
            )
            if existing_svc.scalar_one_or_none() is not None:
                logger.info("Service %s already exists for tenant %s, skipping", svc_name, tenant_slug)
                continue

            svc = ManagedService(
                tenant_id=tenant.id,
                name=svc_name,
                service_type=svc_type,
                tier=svc_tier,
                status=ServiceStatus.PROVISIONING,
            )
            db.add(svc)
            try:
                await db.flush()
            except Exception:
                logger.exception("Failed to create service %s for app %s", svc_name, body.slug)
                await db.rollback()
                continue

            # Provision the service (K8s CRD/Everest)
            try:
                provisioner = ManagedServiceProvisioner(k8s)
                await provisioner.provision(svc, tenant.namespace, tenant_slug=tenant.slug)
            except Exception:
                logger.exception("Failed to provision service %s", svc_name)

            await db.commit()

            pending.append({"service_name": svc_name, "service_type": req.service_type})
            logger.info("Auto-created service %s (%s) for app %s", svc_name, req.service_type, body.slug)

        if pending:
            app.pending_services = pending
            await db.commit()
            await db.refresh(app)

    # Connect existing tenant services by name
    if body.connect_services:
        pending_connect: list[dict] = []
        env_from: list[dict] = list(app.env_from_secrets or [])
        app_env = dict(app.env_vars or {})

        for svc_name in body.connect_services:
            svc_result = await db.execute(
                select(ManagedService).where(
                    ManagedService.tenant_id == tenant.id,
                    ManagedService.name == svc_name,
                )
            )
            svc = svc_result.scalar_one_or_none()
            if svc is None:
                logger.warning("connect_services: service '%s' not found in tenant '%s'", svc_name, tenant_slug)
                continue

            if (
                svc.status == ServiceStatus.READY
                and svc.credentials_provisioned
                and svc.secret_name
                and svc.service_namespace
            ):
                # Immediate connect
                if not any(e.get("service_name") == svc_name for e in env_from):
                    env_from.append(
                        {
                            "service_name": svc_name,
                            "secret_name": svc.secret_name,
                            "namespace": svc.service_namespace,
                        }
                    )
                    if svc.connection_hint:
                        url_key = {
                            "postgres": "DATABASE_URL",
                            "mysql": "MYSQL_URL",
                            "mongodb": "MONGODB_URL",
                        }.get(svc.service_type.value)
                        if url_key:
                            app_env[url_key] = svc.connection_hint
                logger.info("Connected service '%s' to app '%s'", svc_name, body.slug)
            else:
                # Service not ready yet → add to pending for auto-connect
                pending_connect.append({"service_name": svc_name, "service_type": svc.service_type.value})
                logger.info("Service '%s' pending → will auto-connect when ready", svc_name)

        app.env_from_secrets = env_from
        app.env_vars = app_env
        if pending_connect:
            app.pending_services = list(app.pending_services or []) + pending_connect
        await db.commit()
        await db.refresh(app)

    await audit(
        db,
        tenant_id=tenant.id,
        action="app.create",
        user_id=current_user.get("sub", ""),
        resource_type="application",
        resource_id=str(app.id),
        extra={
            "requested_services": [s.service_type for s in (body.requested_services or [])],
            "connect_services": body.connect_services or [],
        },
    )

    return app


@router.get("/{app_slug}", response_model=ApplicationResponse)
async def get_application(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    db: DBSession,
    tenant: TenantMembership,
) -> Application:
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
    tenant: TenantMembership,
    current_user: CurrentUser,
    queue: GitQueueDep,
) -> Application:
    result = await db.execute(
        select(Application).where(Application.tenant_id == tenant.id, Application.slug == app_slug)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    updated_fields = body.model_dump(exclude_none=True)

    # If repo_url changes, clear image_tag to prevent deploying old repo's image
    if "repo_url" in updated_fields and updated_fields["repo_url"] != app.repo_url:
        app.image_tag = None
        logger.info("Cleared image_tag for app %s due to repo_url change", app_slug)

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

    await audit(
        db,
        tenant_id=tenant.id,
        action="app.update",
        user_id=current_user.get("sub", ""),
        resource_type="application",
        resource_id=str(app.id),
        extra={"updated_fields": list(updated_fields.keys())},
    )

    return app


class _SecretVarsBody(BaseModel):
    """Request body for PUT /secrets — key-value pairs for sensitive env vars."""

    secrets: dict[str, str]


@router.put("/{app_slug}/secrets", response_model=dict)
async def upsert_secrets(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    body: _SecretVarsBody,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
) -> dict:
    """Write sensitive env vars to Vault (or K8s Secret fallback).

    These are injected into the pod via envFrom.secretRef and never stored in GitOps.
    """
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
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
) -> dict:
    """List sensitive env var keys (values never returned via API)."""
    app = await _get_app_or_404(tenant.id, app_slug, db)

    from app.services.secret_service import SecretService

    svc = SecretService(k8s)
    if svc.uses_vault():
        from app.services.vault_service import vault_service

        keys = await vault_service.list_keys(tenant.slug, app.slug)
    else:
        keys = svc.list_secret_keys(tenant.namespace, app.slug)
    return {"keys": keys, "vault": svc.uses_vault()}


@router.post("/{app_slug}/restart", status_code=status.HTTP_202_ACCEPTED)
async def restart_application(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
    current_user: CurrentUser,
) -> dict:
    """Restart all pods of an application via rollout restart."""
    app = await _get_app_or_404(tenant.id, app_slug, db)

    if not k8s.is_available():
        raise HTTPException(status_code=503, detail="Kubernetes cluster not available")

    import asyncio
    from datetime import datetime

    try:
        # Patch deployment with restart annotation to trigger rollout restart
        patch_body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "haven.nl/restartedAt": datetime.now(UTC).isoformat(),
                        }
                    }
                }
            }
        }
        await asyncio.to_thread(
            k8s.apps_v1.patch_namespaced_deployment,
            name=app.slug,
            namespace=tenant.namespace,
            body=patch_body,
        )
        logger.info("Restarted app %s in namespace %s", app.slug, tenant.namespace)
    except Exception as exc:
        logger.warning("Failed to restart app %s: %s", app.slug, exc)
        raise HTTPException(status_code=500, detail=f"Restart failed: {exc}") from exc

    await audit(
        db,
        tenant_id=tenant.id,
        action="app.restart",
        user_id=current_user.get("sub", ""),
        resource_type="application",
        resource_id=str(app.id),
    )

    return {"status": "restarting", "app_slug": app.slug}


@router.delete("/{app_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
    current_user: CurrentUser,
) -> None:
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

    await audit(
        db,
        tenant_id=tenant.id,
        action="app.delete",
        user_id=current_user.get("sub", ""),
        resource_type="application",
        resource_id=str(app.id),
        extra={"slug": app.slug},
    )

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
    tenant: TenantMembership,
    queue: GitQueueDep,
) -> Application:
    """Attach a managed service secret to an app's envFrom list."""
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


@router.get("/{app_slug}/services")
async def get_app_services(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    db: DBSession,
    tenant: TenantMembership,
) -> list[dict]:
    """Get all services connected to or pending for this app.

    Returns enriched list with current service status for the app detail page.
    """
    app = await _get_app_or_404(tenant.id, app_slug, db)

    result: list[dict] = []

    # Connected services (from env_from_secrets)
    for entry in app.env_from_secrets or []:
        svc_name = entry.get("service_name", "")
        svc_result = await db.execute(
            select(ManagedService).where(
                ManagedService.tenant_id == tenant.id,
                ManagedService.name == svc_name,
            )
        )
        svc = svc_result.scalar_one_or_none()
        result.append(
            {
                "service_name": svc_name,
                "service_type": svc.service_type.value if svc else "unknown",
                "tier": svc.tier.value if svc else "dev",
                "status": svc.status.value if svc else "unknown",
                "connection_hint": entry.get("connection_hint", ""),
                "database_url_key": entry.get("database_url_key"),
                "connected": True,
                "pending": False,
            }
        )

    # Pending services (from pending_services)
    for entry in app.pending_services or []:
        svc_name = entry.get("service_name", "")
        # Skip if already in connected list
        if any(r["service_name"] == svc_name for r in result):
            continue
        svc_result = await db.execute(
            select(ManagedService).where(
                ManagedService.tenant_id == tenant.id,
                ManagedService.name == svc_name,
            )
        )
        svc = svc_result.scalar_one_or_none()
        result.append(
            {
                "service_name": svc_name,
                "service_type": entry.get("service_type", svc.service_type.value if svc else "unknown"),
                "tier": svc.tier.value if svc else "dev",
                "status": svc.status.value if svc else "provisioning",
                "connection_hint": svc.connection_hint if svc else None,
                "database_url_key": None,
                "connected": False,
                "pending": True,
                "error_message": svc.error_message if svc else None,
            }
        )

    return result


@router.delete("/{app_slug}/connect-service/{service_name}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_service(
    tenant_slug: str,
    app_slug: str,
    service_name: str,
    db: DBSession,
    tenant: TenantMembership,
    queue: GitQueueDep,
) -> None:
    """Remove a managed service secret from an app's envFrom list."""
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
