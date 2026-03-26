import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.config import settings
from app.deps import ArgoCDDep, DBSession, GitOpsDep, K8sDep, get_session_factory
from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.tenant import Tenant
from app.schemas.deployment import DeploymentResponse
from app.services.deploy_service import DeployService, get_service_secret_names
from app.services.pipeline import run_pipeline

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


@router.post("/build", response_model=DeploymentResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_build(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    gitops: GitOpsDep,
    argocd: ArgoCDDep,
    background_tasks: BackgroundTasks,
) -> Deployment:
    """Manually trigger a full build + deploy pipeline.

    The GitHub token is retrieved from the tenant's stored token in the database
    rather than being passed as a query parameter.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    deployment = Deployment(
        application_id=app.id,
        commit_sha="manual",
        status=DeploymentStatus.PENDING,
    )
    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)

    background_tasks.add_task(
        run_pipeline,
        deployment_id=deployment.id,
        app_id=app.id,
        repo_url=app.repo_url,
        branch=app.branch,
        commit_sha="manual",
        app_slug=app.slug,
        tenant_slug=tenant.slug,
        namespace=tenant.namespace,
        tenant_id=tenant.id,
        env_vars=dict(app.env_vars),
        replicas=app.replicas,
        port=app.port,
        session_factory=get_session_factory(),
        k8s=k8s,
        github_token=tenant.github_token,
        gitops=gitops,
        argocd=argocd,
        custom_domain=app.custom_domain or "",
        health_check_path=app.health_check_path or "",
        resource_cpu_request=app.resource_cpu_request,
        resource_cpu_limit=app.resource_cpu_limit,
        resource_memory_request=app.resource_memory_request,
        resource_memory_limit=app.resource_memory_limit,
        min_replicas=app.min_replicas,
        max_replicas=app.max_replicas,
        cpu_threshold=app.cpu_threshold,
    )
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
            port=app.port,
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
            port=app.port,
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
    token: str | None = None,  # noqa: ARG001 — accepted for EventSource auth (validated upstream)
) -> StreamingResponse:
    """Stream pod logs (or build logs if building) via SSE.

    Accepts an optional `token` query param so that browser EventSource
    (which cannot set custom headers) can authenticate.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db)
    app = await _get_app_or_404(tenant.id, app_slug, db)
    namespace = tenant.namespace
    selector = f"app={app.slug}"

    # Preload latest deployment to check for active builds
    result = await db.execute(
        select(Deployment)
        .where(Deployment.application_id == app.id)
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    latest_deployment = result.scalar_one_or_none()

    async def _generate():  # type: ignore[return]
        try:
            # 1) If K8s is not available, try to show build status from DB
            if not k8s.is_available():
                if latest_deployment and latest_deployment.status in (
                    DeploymentStatus.BUILDING,
                    DeploymentStatus.PENDING,
                ):
                    yield f"data: [build in progress — status: {latest_deployment.status.value}]\n\n"
                    if latest_deployment.build_job_name:
                        yield f"data: [build job: {latest_deployment.build_job_name}]\n\n"
                else:
                    yield "data: [kubernetes cluster not available]\n\n"
                yield "data: [end]\n\n"
                return

            # 2) Check if there's an active build — show build logs
            if latest_deployment and latest_deployment.status in (
                DeploymentStatus.BUILDING,
                DeploymentStatus.PENDING,
            ):
                yield "data: [build in progress...]\n\n"
                if latest_deployment.build_job_name:
                    yield f"data: [build job: {latest_deployment.build_job_name}]\n\n"
                    # Stream build pod logs from haven-builds namespace
                    try:
                        build_pods = await asyncio.to_thread(
                            k8s.core_v1.list_namespaced_pod,
                            namespace=settings.build_namespace,
                            label_selector=f"job-name={latest_deployment.build_job_name}",
                        )
                        if build_pods.items:
                            build_pod = build_pods.items[0].metadata.name
                            phase = build_pods.items[0].status.phase
                            yield f"data: [build pod: {build_pod} ({phase})]\n\n"
                            if phase in ("Running", "Succeeded", "Failed"):
                                # Try each container in order
                                for container in ("git-clone", "nixpacks", "kaniko"):
                                    try:
                                        blog: str = await asyncio.to_thread(
                                            k8s.core_v1.read_namespaced_pod_log,
                                            name=build_pod,
                                            namespace=settings.build_namespace,
                                            container=container,
                                            tail_lines=tail_lines,
                                        )
                                        if blog.strip():
                                            yield f"data: --- {container} ---\n\n"
                                            for line in blog.splitlines():
                                                yield f"data: {line}\n\n"
                                    except Exception:  # noqa: BLE001
                                        pass  # container may not have started yet
                        else:
                            yield "data: [waiting for build pod to start...]\n\n"
                    except Exception as exc:  # noqa: BLE001
                        yield f"data: [could not fetch build logs: {exc}]\n\n"
                yield "data: [end]\n\n"
                return

            # 3) Normal case: stream running pod logs
            pods = await asyncio.to_thread(
                k8s.core_v1.list_namespaced_pod,
                namespace=namespace,
                label_selector=selector,
            )
            if not pods.items:
                # Check if the latest deployment failed
                if latest_deployment and latest_deployment.status == DeploymentStatus.FAILED:
                    yield "data: [latest deployment failed]\n\n"
                    if latest_deployment.error_message:
                        for line in latest_deployment.error_message.splitlines()[:50]:
                            yield f"data: {line}\n\n"
                else:
                    yield "data: [no pods running for this application]\n\n"
                yield "data: [end]\n\n"
                return

            pod_name: str = pods.items[0].metadata.name
            phase = pods.items[0].status.phase
            yield f"data: [pod: {pod_name} ({phase})]\n\n"

            logs: str = await asyncio.to_thread(
                k8s.core_v1.read_namespaced_pod_log,
                name=pod_name,
                namespace=namespace,
                tail_lines=tail_lines,
            )
            for line in logs.splitlines():
                yield f"data: {line}\n\n"
            yield "data: [end]\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Log streaming error for %s/%s", namespace, app_slug)
            yield f"data: [error: {exc}]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
    port: int = 8000,
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
            port=port,
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

    # Wait for at least 1 ready replica before marking as RUNNING
    ready, msg = await deploy_svc.wait_for_ready(namespace, app_slug)
    if not ready:
        logger.error("Redeploy not ready: %s (deployment=%s)", msg, deployment_id)
        async with session_factory() as db:
            dep = await db.get(_Deployment, deployment_id)
            if dep:
                dep.status = DeploymentStatus.FAILED
                dep.error_message = msg[:4096]
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
