"""Environments router — staging and PR preview environments per application.

H3e (P2.5 / P18 batch 2): migrated to canonical `TenantMembership`
dependency from `app/deps.py`. The local `_get_tenant_or_404` helper has
been removed.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.deps import DBSession, K8sDep, TenantMembership
from app.models.application import Application
from app.models.environment import Environment, EnvironmentStatus, EnvironmentType
from app.models.tenant import Tenant
from app.schemas.environment import EnvironmentCreate, EnvironmentResponse, EnvironmentUpdate

router = APIRouter(prefix="/tenants/{tenant_slug}/apps/{app_slug}/environments", tags=["environments"])
logger = logging.getLogger(__name__)


def _compute_namespace(tenant_slug: str, env: Environment) -> str:
    """Return the K8s namespace for an environment."""
    if env.namespace_override:
        return env.namespace_override
    if env.env_type == EnvironmentType.production:
        return f"tenant-{tenant_slug}"
    if env.env_type == EnvironmentType.staging:
        return f"tenant-{tenant_slug}-staging"
    # preview: pr-<number>
    return f"tenant-{tenant_slug}-pr-{env.pr_number}"


def _compute_domain(tenant_slug: str, app_slug: str, env: Environment) -> str:
    """Return the sslip.io URL for an environment."""
    lb = settings.lb_ip.replace(".", "-")
    base = f"{app_slug}.{tenant_slug}.apps.{lb}.sslip.io"
    if env.env_type == EnvironmentType.production:
        return base
    if env.env_type == EnvironmentType.staging:
        return f"staging-{base}"
    return f"pr-{env.pr_number}-{base}"


async def _get_app_or_404(tenant: Tenant, app_slug: str, db: DBSession) -> Application:
    result = await db.execute(
        select(Application).where(Application.tenant_id == tenant.id, Application.slug == app_slug)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


async def _get_env_or_404(app: Application, env_name: str, db: DBSession) -> Environment:
    result = await db.execute(
        select(Environment).where(Environment.application_id == app.id, Environment.name == env_name)
    )
    env = result.scalar_one_or_none()
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    return env


@router.get("", response_model=list[EnvironmentResponse])
async def list_environments(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    db: DBSession,
    tenant: TenantMembership,
) -> list[Environment]:
    app = await _get_app_or_404(tenant, app_slug, db)
    result = await db.execute(
        select(Environment).where(Environment.application_id == app.id).order_by(Environment.created_at.asc())
    )
    return list(result.scalars().all())


@router.post("", response_model=EnvironmentResponse, status_code=status.HTTP_201_CREATED)
async def create_environment(
    tenant_slug: str,
    app_slug: str,
    body: EnvironmentCreate,
    db: DBSession,
    tenant: TenantMembership,
) -> Environment:
    app = await _get_app_or_404(tenant, app_slug, db)

    # Prevent duplicate names within an app
    existing = await db.execute(
        select(Environment).where(Environment.application_id == app.id, Environment.name == body.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Environment '{body.name}' already exists")

    env = Environment(
        application_id=app.id,
        name=body.name,
        env_type=body.env_type,
        branch=body.branch,
        env_vars=body.env_vars,
        replicas=body.replicas,
    )
    db.add(env)
    # Compute domain after we have an id
    await db.flush()
    env.domain = _compute_domain(tenant_slug, app_slug, env)
    await db.commit()
    await db.refresh(env)
    return env


@router.get("/{env_name}", response_model=EnvironmentResponse)
async def get_environment(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    env_name: str,
    db: DBSession,
    tenant: TenantMembership,
) -> Environment:
    app = await _get_app_or_404(tenant, app_slug, db)
    return await _get_env_or_404(app, env_name, db)


@router.patch("/{env_name}", response_model=EnvironmentResponse)
async def update_environment(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    env_name: str,
    body: EnvironmentUpdate,
    db: DBSession,
    tenant: TenantMembership,
) -> Environment:
    app = await _get_app_or_404(tenant, app_slug, db)
    env = await _get_env_or_404(app, env_name, db)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(env, field, value)

    await db.commit()
    await db.refresh(env)
    return env


@router.delete("/{env_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_environment(
    tenant_slug: str,
    app_slug: str,
    env_name: str,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
) -> None:
    app = await _get_app_or_404(tenant, app_slug, db)
    env = await _get_env_or_404(app, env_name, db)

    if env.env_type == EnvironmentType.production:
        raise HTTPException(status_code=400, detail="Cannot delete the production environment")

    # Mark as deleting first so UI shows correct state
    env.status = EnvironmentStatus.deleting
    await db.commit()

    # Best-effort K8s namespace cleanup
    ns = _compute_namespace(tenant_slug, env)
    if k8s.is_available() and k8s.core_v1 is not None:
        try:
            k8s.core_v1.delete_namespace(ns)
            logger.info("Deleted K8s namespace %s for environment %s", ns, env.name)
        except Exception:
            logger.warning("Could not delete namespace %s — may not exist", ns)

    await db.delete(env)
    await db.commit()
