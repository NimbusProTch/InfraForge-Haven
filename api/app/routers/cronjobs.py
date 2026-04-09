"""CronJob management endpoints.

Sprint 11: K8s CronJob CRUD — create, list, get, update, delete, run-now.
CronJobs are scoped to a tenant's application and run in the tenant's namespace.

H3e (P2.5): migrated to canonical `TenantMembership` dependency from
`app/deps.py`. The local `_get_tenant_or_404` helper has been removed.
"""

import asyncio
import logging
import re
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DBSession, K8sDep, TenantMembership
from app.models.application import Application
from app.models.cronjob import CronJob
from app.schemas.cronjob import CronJobCreate, CronJobResponse, CronJobUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/apps/{app_slug}/cronjobs", tags=["cronjobs"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_app_or_404(tenant_id: uuid.UUID, app_slug: str, db: DBSession) -> Application:
    result = await db.execute(
        select(Application).where(Application.tenant_id == tenant_id, Application.slug == app_slug)
    )
    a = result.scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return a


async def _get_cronjob_or_404(app_id: uuid.UUID, cronjob_id: uuid.UUID, db: DBSession) -> CronJob:
    result = await db.execute(select(CronJob).where(CronJob.id == cronjob_id, CronJob.application_id == app_id))
    cj = result.scalar_one_or_none()
    if cj is None:
        raise HTTPException(status_code=404, detail="CronJob not found")
    return cj


def _k8s_cronjob_name(app_slug: str, cj_name: str) -> str:
    """Generate a valid K8s resource name from app + cronjob name."""
    raw = f"{app_slug}-{cj_name}".lower()
    sanitized = re.sub(r"[^a-z0-9-]", "-", raw)[:52]
    return sanitized.strip("-")


def _build_k8s_cronjob(cj: CronJob, app: Application, namespace: str) -> dict:
    """Build the K8s CronJob manifest from a CronJob model."""
    env_list = []
    for k, v in (cj.env_vars or app.env_vars or {}).items():
        env_list.append({"name": k, "value": v})

    container: dict = {
        "name": "job",
        "image": app.image_tag or "busybox:latest",
        "env": env_list,
        "resources": {
            "requests": {"cpu": cj.cpu_request, "memory": cj.memory_request},
            "limits": {"cpu": cj.cpu_limit, "memory": cj.memory_limit},
        },
    }
    if cj.command:
        container["command"] = cj.command

    spec: dict = {
        "concurrencyPolicy": cj.concurrency_policy,
        "successfulJobsHistoryLimit": cj.successful_jobs_history,
        "failedJobsHistoryLimit": cj.failed_jobs_history,
        "suspend": cj.suspended,
        "jobTemplate": {
            "spec": {
                "template": {
                    "metadata": {"labels": {"app": app.slug, "cronjob": cj.name}},
                    "spec": {
                        "restartPolicy": "OnFailure",
                        "containers": [container],
                    },
                }
            }
        },
        "schedule": cj.schedule,
    }
    if cj.starting_deadline_seconds is not None:
        spec["startingDeadlineSeconds"] = cj.starting_deadline_seconds

    return {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {
            "name": cj.k8s_name,
            "namespace": namespace,
            "labels": {"app": app.slug, "tenant": namespace, "haven-cronjob": "true"},
        },
        "spec": spec,
    }


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CronJobResponse])
async def list_cronjobs(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    db: DBSession,
    tenant: TenantMembership,
) -> list[CronJob]:
    """List all CronJobs for an application."""
    app = await _get_app_or_404(tenant.id, app_slug, db)

    result = await db.execute(
        select(CronJob).where(CronJob.application_id == app.id).order_by(CronJob.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=CronJobResponse, status_code=status.HTTP_201_CREATED)
async def create_cronjob(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    body: CronJobCreate,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
) -> CronJob:
    """Create a K8s CronJob for an application."""
    app = await _get_app_or_404(tenant.id, app_slug, db)

    k8s_name = _k8s_cronjob_name(app.slug, body.name)

    cj = CronJob(
        application_id=app.id,
        name=body.name,
        schedule=body.schedule,
        command=body.command,
        cpu_request=body.cpu_request,
        cpu_limit=body.cpu_limit,
        memory_request=body.memory_request,
        memory_limit=body.memory_limit,
        concurrency_policy=body.concurrency_policy,
        successful_jobs_history=body.successful_jobs_history,
        failed_jobs_history=body.failed_jobs_history,
        starting_deadline_seconds=body.starting_deadline_seconds,
        suspended=body.suspended,
        env_vars=body.env_vars,
        description=body.description,
        k8s_name=k8s_name,
    )
    db.add(cj)
    await db.commit()
    await db.refresh(cj)

    # Apply to K8s if available
    if k8s.is_available():
        manifest = _build_k8s_cronjob(cj, app, tenant.namespace)
        try:
            await asyncio.to_thread(
                k8s.batch_v1.create_namespaced_cron_job,
                namespace=tenant.namespace,
                body=manifest,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("K8s CronJob creation failed (DB record kept): %s", exc)

    return cj


@router.get("/{cronjob_id}", response_model=CronJobResponse)
async def get_cronjob(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    cronjob_id: uuid.UUID,
    db: DBSession,
    tenant: TenantMembership,
) -> CronJob:
    app = await _get_app_or_404(tenant.id, app_slug, db)
    return await _get_cronjob_or_404(app.id, cronjob_id, db)


@router.patch("/{cronjob_id}", response_model=CronJobResponse)
async def update_cronjob(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    cronjob_id: uuid.UUID,
    body: CronJobUpdate,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
) -> CronJob:
    """Update a CronJob (schedule, resources, suspend state, etc.)."""
    app = await _get_app_or_404(tenant.id, app_slug, db)
    cj = await _get_cronjob_or_404(app.id, cronjob_id, db)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(cj, field, value)

    await db.commit()
    await db.refresh(cj)

    # Sync to K8s
    if k8s.is_available() and cj.k8s_name:
        manifest = _build_k8s_cronjob(cj, app, tenant.namespace)
        try:
            await asyncio.to_thread(
                k8s.batch_v1.patch_namespaced_cron_job,
                name=cj.k8s_name,
                namespace=tenant.namespace,
                body=manifest,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("K8s CronJob patch failed: %s", exc)

    return cj


@router.delete("/{cronjob_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cronjob(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    cronjob_id: uuid.UUID,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
) -> None:
    """Delete a CronJob from DB and K8s."""
    app = await _get_app_or_404(tenant.id, app_slug, db)
    cj = await _get_cronjob_or_404(app.id, cronjob_id, db)

    # Delete from K8s first
    if k8s.is_available() and cj.k8s_name:
        try:
            await asyncio.to_thread(
                k8s.batch_v1.delete_namespaced_cron_job,
                name=cj.k8s_name,
                namespace=tenant.namespace,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("K8s CronJob delete failed (continuing DB delete): %s", exc)

    await db.delete(cj)
    await db.commit()


@router.post("/{cronjob_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_cronjob_now(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    cronjob_id: uuid.UUID,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
) -> dict:
    """Trigger an immediate one-off run of a CronJob (creates a K8s Job from the CronJob template)."""
    app = await _get_app_or_404(tenant.id, app_slug, db)
    cj = await _get_cronjob_or_404(app.id, cronjob_id, db)

    if not k8s.is_available():
        raise HTTPException(status_code=503, detail="Kubernetes cluster not available")

    if not cj.k8s_name:
        raise HTTPException(status_code=409, detail="CronJob has no K8s resource name — create it first")

    # Fetch the CronJob from K8s to get its job template
    try:
        k8s_cj = await asyncio.to_thread(
            k8s.batch_v1.read_namespaced_cron_job,
            name=cj.k8s_name,
            namespace=tenant.namespace,
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"K8s CronJob not found: {exc}") from exc

    # Build a one-off Job from the CronJob's job template
    from datetime import UTC, datetime

    run_name = f"{cj.k8s_name}-manual-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    job_spec = k8s_cj.spec.job_template.spec

    job_manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": run_name,
            "namespace": tenant.namespace,
            "labels": {"haven-manual-run": "true", "cronjob": cj.k8s_name},
        },
        "spec": {
            "template": {
                "metadata": (
                    job_spec.template.metadata.to_dict() if hasattr(job_spec.template.metadata, "to_dict") else {}
                ),
                "spec": job_spec.template.spec.to_dict() if hasattr(job_spec.template.spec, "to_dict") else {},
            }
        },
    }

    try:
        await asyncio.to_thread(
            k8s.batch_v1.create_namespaced_job,
            namespace=tenant.namespace,
            body=job_manifest,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to trigger run: {exc}") from exc

    return {"message": "CronJob triggered", "job_name": run_name}
