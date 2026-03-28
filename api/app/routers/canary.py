"""Canary deploy management endpoints.

Sprint 11: Canary deploy via Cilium Gateway API traffic splitting.
- Enable/disable canary mode for an application
- Set canary traffic weight (0-100%)
- Promote canary to stable (100% traffic)
- Rollback canary (0% traffic → disable)

Traffic is split at the HTTPRoute level using Cilium Gateway API weights.
Canary deployment uses a separate K8s Deployment ({app_slug}-canary).
"""

import asyncio
import contextlib
import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import CurrentUser, DBSession, K8sDep
from app.models.application import Application
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/apps/{app_slug}/canary", tags=["canary"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CanaryConfig(BaseModel):
    enabled: bool
    weight: int = Field(default=10, ge=0, le=100, description="Percentage of traffic sent to canary (0-100)")
    canary_image: str | None = Field(default=None, max_length=512, description="Image tag for canary deployment")


class CanaryStatus(BaseModel):
    enabled: bool
    weight: int
    stable_image: str | None
    canary_image: str | None
    canary_replicas: int | None = None
    stable_replicas: int | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    t = result.scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return t


async def _get_app_or_404(tenant_id: uuid.UUID, app_slug: str, db: DBSession) -> Application:
    result = await db.execute(
        select(Application).where(Application.tenant_id == tenant_id, Application.slug == app_slug)
    )
    a = result.scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return a


def _build_canary_deployment(app: Application, namespace: str, canary_image: str) -> dict:
    """Build a canary K8s Deployment manifest."""
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": f"{app.slug}-canary",
            "namespace": namespace,
            "labels": {"app": app.slug, "track": "canary"},
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": app.slug, "track": "canary"}},
            "template": {
                "metadata": {"labels": {"app": app.slug, "track": "canary"}},
                "spec": {
                    "containers": [
                        {
                            "name": app.slug,
                            "image": canary_image,
                            "ports": [{"containerPort": app.port}],
                            "resources": {
                                "requests": {
                                    "cpu": app.resource_cpu_request,
                                    "memory": app.resource_memory_request,
                                },
                                "limits": {
                                    "cpu": app.resource_cpu_limit,
                                    "memory": app.resource_memory_limit,
                                },
                            },
                        }
                    ]
                },
            },
        },
    }


def _build_canary_service(app: Application, namespace: str) -> dict:
    """Build the canary K8s Service manifest."""
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": f"{app.slug}-canary",
            "namespace": namespace,
        },
        "spec": {
            "selector": {"app": app.slug, "track": "canary"},
            "ports": [{"port": 80, "targetPort": app.port}],
        },
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=CanaryStatus)
async def get_canary_status(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> CanaryStatus:
    """Get current canary deployment status."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    canary_image = None
    canary_replicas = None
    stable_replicas = None

    if k8s.is_available() and app.canary_enabled:
        try:
            canary_dep = await asyncio.to_thread(
                k8s.apps_v1.read_namespaced_deployment,
                name=f"{app.slug}-canary",
                namespace=tenant.namespace,
            )
            canary_image = canary_dep.spec.template.spec.containers[0].image
            canary_replicas = canary_dep.status.ready_replicas or 0
        except Exception:  # noqa: BLE001
            pass

        try:
            stable_dep = await asyncio.to_thread(
                k8s.apps_v1.read_namespaced_deployment,
                name=app.slug,
                namespace=tenant.namespace,
            )
            stable_replicas = stable_dep.status.ready_replicas or 0
        except Exception:  # noqa: BLE001
            pass

    return CanaryStatus(
        enabled=app.canary_enabled,
        weight=app.canary_weight,
        stable_image=app.image_tag,
        canary_image=canary_image,
        canary_replicas=canary_replicas,
        stable_replicas=stable_replicas,
    )


@router.put("", response_model=CanaryStatus, status_code=status.HTTP_200_OK)
async def configure_canary(
    tenant_slug: str,
    app_slug: str,
    config: CanaryConfig,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> CanaryStatus:
    """Enable/disable canary and set traffic weight.

    When enabling canary:
    - Creates a {app_slug}-canary Deployment with the canary_image
    - Creates a {app_slug}-canary Service
    - The HTTPRoute weight split is applied at the Cilium Gateway level

    When disabling:
    - Deletes canary Deployment and Service
    - All traffic returns to stable
    """
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    if config.enabled and not config.canary_image and not app.canary_enabled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="canary_image is required when enabling canary for the first time",
        )

    canary_image = config.canary_image or app.image_tag

    # Update DB state
    app.canary_enabled = config.enabled
    app.canary_weight = config.weight
    await db.commit()
    await db.refresh(app)

    if k8s.is_available():
        if config.enabled and canary_image:
            # Create/update canary deployment
            canary_manifest = _build_canary_deployment(app, tenant.namespace, canary_image)
            try:
                await asyncio.to_thread(
                    k8s.apps_v1.patch_namespaced_deployment,
                    name=f"{app.slug}-canary",
                    namespace=tenant.namespace,
                    body=canary_manifest,
                )
            except Exception:  # noqa: BLE001
                try:
                    await asyncio.to_thread(
                        k8s.apps_v1.create_namespaced_deployment,
                        namespace=tenant.namespace,
                        body=canary_manifest,
                    )
                except Exception as exc2:  # noqa: BLE001
                    logger.warning("Canary deployment creation failed: %s", exc2)

            # Create/update canary service
            svc_manifest = _build_canary_service(app, tenant.namespace)
            try:
                await asyncio.to_thread(
                    k8s.core_v1.patch_namespaced_service,
                    name=f"{app.slug}-canary",
                    namespace=tenant.namespace,
                    body=svc_manifest,
                )
            except Exception:  # noqa: BLE001
                try:
                    await asyncio.to_thread(
                        k8s.core_v1.create_namespaced_service,
                        namespace=tenant.namespace,
                        body=svc_manifest,
                    )
                except Exception as exc2:  # noqa: BLE001
                    logger.warning("Canary service creation failed: %s", exc2)

        elif not config.enabled:
            # Clean up canary resources
            for cleanup in [
                (k8s.apps_v1.delete_namespaced_deployment, f"{app.slug}-canary", tenant.namespace),
                (k8s.core_v1.delete_namespaced_service, f"{app.slug}-canary", tenant.namespace),
            ]:
                with contextlib.suppress(Exception):  # already gone
                    await asyncio.to_thread(cleanup[0], name=cleanup[1], namespace=cleanup[2])

    return CanaryStatus(
        enabled=app.canary_enabled,
        weight=app.canary_weight,
        stable_image=app.image_tag,
        canary_image=canary_image,
    )


@router.post("/promote", status_code=status.HTTP_200_OK)
async def promote_canary(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> dict:
    """Promote canary to stable: update stable image to canary image, disable canary.

    This effectively makes the canary the new stable version.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    if not app.canary_enabled:
        raise HTTPException(status_code=409, detail="Canary is not enabled for this application")

    canary_image = None
    if k8s.is_available():
        try:
            canary_dep = await asyncio.to_thread(
                k8s.apps_v1.read_namespaced_deployment,
                name=f"{app.slug}-canary",
                namespace=tenant.namespace,
            )
            canary_image = canary_dep.spec.template.spec.containers[0].image
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Canary deployment not found: {exc}") from exc

    if canary_image:
        app.image_tag = canary_image

    app.canary_enabled = False
    app.canary_weight = 10
    await db.commit()

    # Clean up canary K8s resources
    if k8s.is_available():
        for cleanup in [
            (k8s.apps_v1.delete_namespaced_deployment, f"{app.slug}-canary"),
            (k8s.core_v1.delete_namespaced_service, f"{app.slug}-canary"),
        ]:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(cleanup[0], name=cleanup[1], namespace=tenant.namespace)

    return {"message": "Canary promoted to stable", "new_image": canary_image or app.image_tag}


@router.post("/rollback", status_code=status.HTTP_200_OK)
async def rollback_canary(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> dict:
    """Rollback canary: disable canary, all traffic returns to stable."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    if not app.canary_enabled:
        raise HTTPException(status_code=409, detail="Canary is not enabled for this application")

    app.canary_enabled = False
    app.canary_weight = 10
    await db.commit()

    # Remove canary K8s resources
    if k8s.is_available():
        for cleanup in [
            (k8s.apps_v1.delete_namespaced_deployment, f"{app.slug}-canary"),
            (k8s.core_v1.delete_namespaced_service, f"{app.slug}-canary"),
        ]:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(cleanup[0], name=cleanup[1], namespace=tenant.namespace)

    return {"message": "Canary rolled back, all traffic on stable"}
