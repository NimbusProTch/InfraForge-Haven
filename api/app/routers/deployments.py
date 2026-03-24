import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.deps import DBSession, K8sDep, get_session_factory
from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.tenant import Tenant
from app.schemas.deployment import DeploymentResponse
from app.services.deploy_service import DeployService, get_service_secret_names

router = APIRouter(prefix="/tenants/{tenant_slug}/apps/{app_slug}", tags=["deployments"])
logger = logging.getLogger(__name__)


async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


async def _get_app_or_404(tenant_id: uuid.UUID, app_slug: str, db: DBSession) -> Application:
    result = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant_id,
            Application.slug == app_slug,
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.get("/deployments", response_model=list[DeploymentResponse])
async def list_deployments(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    limit: int = 20,
) -> list[Deployment]:
    """List recent deployments for an application (newest first)."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    result = await db.execute(
        select(Deployment)
        .where(Deployment.application_id == app.id)
        .order_by(Deployment.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get("/deployments/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    tenant_slug: str,
    app_slug: str,
    deployment_id: uuid.UUID,
    db: DBSession,
) -> Deployment:
    """Get a single deployment by ID."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    result = await db.execute(
        select(Deployment).where(
            Deployment.id == deployment_id,
            Deployment.application_id == app.id,
        )
    )
    deployment = result.scalar_one_or_none()
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


@router.post("/deploy", response_model=DeploymentResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_deploy(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
) -> Deployment:
    """Manually trigger a deployment for the current image_tag."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    if not app.image_tag:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No image built for this application yet. Push a commit to trigger a build.",
        )

    deployment = Deployment(
        application_id=app.id,
        commit_sha="manual",
        status=DeploymentStatus.PENDING,
        image_tag=app.image_tag,
    )
    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)

    secret_names = await get_service_secret_names(db, tenant.id)

    asyncio.create_task(
        _run_redeploy(
            deployment_id=deployment.id,
            app_id=app.id,
            app_slug=app.slug,
            tenant_slug=tenant.slug,
            namespace=tenant.namespace,
            image=app.image_tag,
            replicas=app.replicas,
            env_vars=dict(app.env_vars),
            service_secret_names=secret_names,
            k8s=k8s,
        ),
        name=f"redeploy-{deployment.id}",
    )

    return deployment


@router.post(
    "/deployments/{deployment_id}/rollback",
    response_model=DeploymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rollback_deployment(
    tenant_slug: str,
    app_slug: str,
    deployment_id: uuid.UUID,
    db: DBSession,
    k8s: K8sDep,
) -> Deployment:
    """Roll back to a specific past deployment's image."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    result = await db.execute(
        select(Deployment).where(
            Deployment.id == deployment_id,
            Deployment.application_id == app.id,
        )
    )
    target_deployment = result.scalar_one_or_none()
    if target_deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if not target_deployment.image_tag:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Target deployment has no image_tag to roll back to",
        )

    rollback_record = Deployment(
        application_id=app.id,
        commit_sha=f"rollback-to-{deployment_id}",
        status=DeploymentStatus.DEPLOYING,
        image_tag=target_deployment.image_tag,
    )
    db.add(rollback_record)
    await db.commit()
    await db.refresh(rollback_record)

    secret_names = await get_service_secret_names(db, tenant.id)

    asyncio.create_task(
        _run_redeploy(
            deployment_id=rollback_record.id,
            app_id=app.id,
            app_slug=app.slug,
            tenant_slug=tenant.slug,
            namespace=tenant.namespace,
            image=target_deployment.image_tag,
            replicas=app.replicas,
            env_vars=dict(app.env_vars),
            service_secret_names=secret_names,
            k8s=k8s,
        ),
        name=f"rollback-{rollback_record.id}",
    )
    return rollback_record


@router.get("/logs")
async def stream_logs(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    tail_lines: int = 100,
) -> StreamingResponse:
    """Stream the latest pod logs for a running application via SSE."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)
    namespace = tenant.namespace
    selector = f"app={app.slug}"

    if not k8s.is_available():
        raise HTTPException(status_code=503, detail="Kubernetes client not available")

    async def _generate():  # type: ignore[return]
        try:
            pods = await asyncio.to_thread(
                k8s.core_v1.list_namespaced_pod,
                namespace=namespace,
                label_selector=selector,
            )
            if not pods.items:
                yield "data: [no pods running for this application]\n\n"
                return

            pod_name: str = pods.items[0].metadata.name
            logs: str = await asyncio.to_thread(
                k8s.core_v1.read_namespaced_pod_log,
                name=pod_name,
                namespace=namespace,
                tail_lines=tail_lines,
            )
            for line in logs.splitlines():
                yield f"data: {line}\n\n"
            yield "data: [end of logs]\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Log streaming error for %s/%s", namespace, app_slug)
            yield f"data: [error: {exc}]\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


async def _run_redeploy(
    *,
    deployment_id: uuid.UUID,
    app_id: uuid.UUID,
    app_slug: str,
    tenant_slug: str,
    namespace: str,
    image: str,
    replicas: int,
    env_vars: dict[str, str],
    service_secret_names: list[str],
    k8s,  # type: ignore[type-arg]
) -> None:
    """Re-deploy an existing image without going through the build step."""
    from app.models.deployment import Deployment as _Deployment

    session_factory = get_session_factory()
    deploy_svc = DeployService(k8s)

    async with session_factory() as db:
        dep = await db.get(_Deployment, deployment_id)
        if dep:
            dep.status = DeploymentStatus.DEPLOYING
            await db.commit()

    try:
        await deploy_svc.deploy(
            namespace=namespace,
            tenant_slug=tenant_slug,
            app_slug=app_slug,
            image=image,
            replicas=replicas,
            env_vars=env_vars,
            service_secret_names=service_secret_names,
        )
    except Exception as exc:
        logger.exception("Redeploy failed for deployment %s", deployment_id)
        async with session_factory() as db:
            dep = await db.get(_Deployment, deployment_id)
            if dep:
                dep.status = DeploymentStatus.FAILED
                dep.error_message = str(exc)[:4096]
                await db.commit()
        return

    async with session_factory() as db:
        dep = await db.get(_Deployment, deployment_id)
        if dep:
            dep.status = DeploymentStatus.RUNNING
            await db.commit()
        app = await db.get(Application, app_id)
        if app:
            app.image_tag = image
            await db.commit()
