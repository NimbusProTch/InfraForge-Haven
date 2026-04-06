import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.config import settings
from app.deps import ArgoCDDep, CurrentUser, DBSession, GitOpsDep, K8sDep, get_session_factory
from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.tenant import Tenant
from app.schemas.deployment import DeploymentResponse
from app.services.audit_service import audit
from app.services.deploy_service import DeployService, get_service_secret_names
from app.services.pipeline import run_pipeline

router = APIRouter(prefix="/tenants/{tenant_slug}/apps/{app_slug}", tags=["deployments"])
logger = logging.getLogger(__name__)


async def _get_tenant_or_404(tenant_slug: str, db: DBSession, current_user: dict | None = None) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if current_user:
        from app.models.tenant_member import TenantMember

        uid = current_user.get("sub", "")
        mem = await db.execute(
            select(TenantMember).where(TenantMember.tenant_id == tenant.id, TenantMember.user_id == uid)
        )
        if mem.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="You are not a member of this tenant")
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
    current_user: CurrentUser,
    limit: int = 20,
) -> list[Deployment]:
    """List recent deployments for an application (newest first)."""
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
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
    current_user: CurrentUser,
) -> Deployment:
    """Get a single deployment by ID."""
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
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


@router.get("/build-status")
async def get_build_status(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> dict:
    """Get per-container build status for the latest deployment's build job.

    Returns status of each init container (git-clone, nixpacks, buildctl)
    so the UI can show granular pipeline step progress.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    # Find latest deployment with a build job
    result = await db.execute(
        select(Deployment)
        .where(Deployment.application_id == app.id, Deployment.build_job_name.isnot(None))
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    deployment = result.scalar_one_or_none()
    if not deployment or not deployment.build_job_name:
        return {"job_name": None, "containers": [], "status": "no_build"}

    if not k8s.is_available():
        return {"job_name": deployment.build_job_name, "containers": [], "status": "k8s_unavailable"}

    # Query build pod status from K8s
    containers = []
    try:
        pods = await asyncio.to_thread(
            k8s.core_v1.list_namespaced_pod,
            namespace=settings.build_namespace,
            label_selector=f"job-name={deployment.build_job_name}",
        )
        if pods.items:
            pod = pods.items[0]
            # Init containers (git-clone, nixpacks, buildctl)
            for cs in pod.status.init_container_statuses or []:
                container = {
                    "name": cs.name,
                    "status": "pending",
                    "exit_code": None,
                    "duration": None,
                }
                if cs.state.terminated:
                    t = cs.state.terminated
                    container["status"] = "completed" if t.exit_code == 0 else "failed"
                    container["exit_code"] = t.exit_code
                    if t.started_at and t.finished_at:
                        delta = t.finished_at - t.started_at
                        container["duration"] = f"{delta.total_seconds():.1f}s"
                elif cs.state.running:
                    container["status"] = "running"
                    if cs.state.running.started_at:
                        from datetime import UTC, datetime

                        delta = datetime.now(UTC) - cs.state.running.started_at.replace(tzinfo=UTC)
                        container["duration"] = f"{delta.total_seconds():.0f}s"
                elif cs.state.waiting:
                    container["status"] = "waiting"
                containers.append(container)

            # Main container (buildctl)
            for cs in pod.status.container_statuses or []:
                container = {"name": cs.name, "status": "pending", "exit_code": None, "duration": None}
                if cs.state.terminated:
                    t = cs.state.terminated
                    container["status"] = "completed" if t.exit_code == 0 else "failed"
                    container["exit_code"] = t.exit_code
                elif cs.state.running:
                    container["status"] = "running"
                containers.append(container)
    except Exception as exc:
        logger.warning("Failed to query build pod status: %s", exc)

    return {
        "job_name": deployment.build_job_name,
        "deployment_status": deployment.status.value,
        "containers": containers,
    }


class BuildRequest(BaseModel):
    """Optional request body for build trigger."""

    branch: str | None = Field(None, max_length=255, description="Branch override (uses app default if omitted)")
    build_env_vars: dict[str, str] | None = Field(None, description="Build-time environment variables")

    @field_validator("build_env_vars")
    @classmethod
    def validate_env_vars(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is None:
            return v
        if len(v) > 50:
            raise ValueError("Maximum 50 build environment variables allowed")
        for key, val in v.items():
            if len(key) > 256:
                raise ValueError(f"Env var key too long (max 256): {key[:20]}...")
            if len(val) > 32768:
                raise ValueError(f"Env var value too long (max 32KB): {key}")
        return v


class DeployRequest(BaseModel):
    """Optional request body for deploy trigger."""

    replicas: int | None = Field(None, ge=1, le=10, description="Override replica count")
    resource_cpu_limit: str | None = Field(None, pattern=r"^\d+m?$", description="CPU limit (e.g. 500m, 1)")
    resource_memory_limit: str | None = Field(
        None, pattern=r"^\d+(Mi|Gi)$", description="Memory limit (e.g. 512Mi, 1Gi)"
    )


@router.post("/build", response_model=DeploymentResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_build(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    gitops: GitOpsDep,
    argocd: ArgoCDDep,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    body: BuildRequest | None = None,
    deploy: bool = Query(True, description="If false, build only without deploying (status=BUILT)"),
) -> Deployment:
    """Trigger a build pipeline.

    - deploy=true (default): Full build + deploy pipeline.
    - deploy=false: Build only — image pushed to Harbor, status set to BUILT. Use POST /deploy-image to deploy later.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    branch = (body.branch if body and body.branch else None) or app.branch
    build_env_vars = (body.build_env_vars if body else None) or {}

    # Merge build env vars with app env vars (build vars take precedence)
    env_vars = dict(app.env_vars)
    env_vars.update(build_env_vars)

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
        branch=branch,
        commit_sha="manual",
        app_slug=app.slug,
        tenant_slug=tenant.slug,
        namespace=tenant.namespace,
        tenant_id=tenant.id,
        env_vars=env_vars,
        replicas=app.replicas,
        port=app.port,
        session_factory=get_session_factory(),
        k8s=k8s,
        github_token=tenant.github_token,
        gitops=gitops,
        argocd=argocd,
        dockerfile_path=app.dockerfile_path,
        build_context=app.build_context,
        use_dockerfile=app.use_dockerfile,
        custom_domain=app.custom_domain or "",
        health_check_path=app.health_check_path or "",
        resource_cpu_request=app.resource_cpu_request,
        resource_cpu_limit=app.resource_cpu_limit,
        resource_memory_request=app.resource_memory_request,
        resource_memory_limit=app.resource_memory_limit,
        min_replicas=app.min_replicas,
        max_replicas=app.max_replicas,
        cpu_threshold=app.cpu_threshold,
        app_type=app.app_type or "web",
        deploy=deploy,
    )

    # Enqueue build for queue position tracking (best-effort, does not block pipeline)
    queue_position: int | None = None
    try:
        from app.routers.build_queue import _get_build_queue_service

        queue_svc = _get_build_queue_service()
        if queue_svc is not None:
            _job_id, queue_position = await queue_svc.enqueue_build(
                tenant_slug=tenant_slug,
                app_slug=app_slug,
                deployment_id=str(deployment.id),
            )
    except Exception as exc:
        logger.debug("Build queue enqueue skipped: %s", exc)

    await audit(
        db,
        tenant_id=tenant.id,
        action="deployment.build" if deploy else "deployment.build_only",
        user_id=current_user.get("sub", ""),
        resource_type="deployment",
        resource_id=str(deployment.id),
        extra={
            "app_slug": app.slug,
            "branch": branch,
            "build_env_vars": list(build_env_vars.keys()),
            "queue_position": queue_position,
        },
    )

    return deployment


@router.post("/deploy", response_model=DeploymentResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_deploy(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
    body: DeployRequest | None = None,
) -> Deployment:
    """Manually trigger a deployment for the current image_tag.

    Accepts optional replicas and resource limit overrides.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    if not app.image_tag:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No image built for this application yet. Push a commit to trigger a build.",
        )

    # Apply deploy-time overrides to the app record
    if body:
        if body.replicas is not None:
            app.replicas = body.replicas
        if body.resource_cpu_limit is not None:
            app.resource_cpu_limit = body.resource_cpu_limit
        if body.resource_memory_limit is not None:
            app.resource_memory_limit = body.resource_memory_limit
        await db.commit()
        await db.refresh(app)

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
            resource_cpu_request=app.resource_cpu_request,
            resource_cpu_limit=app.resource_cpu_limit,
            resource_memory_request=app.resource_memory_request,
            resource_memory_limit=app.resource_memory_limit,
            health_check_path=app.health_check_path or "",
            custom_domain=app.custom_domain or "",
            min_replicas=app.min_replicas,
            max_replicas=app.max_replicas,
            cpu_threshold=app.cpu_threshold,
            app_type=app.app_type or "web",
        ),
        name=f"redeploy-{deployment.id}",
    )

    await audit(
        db,
        tenant_id=tenant.id,
        action="deployment.deploy",
        user_id=current_user.get("sub", ""),
        resource_type="deployment",
        resource_id=str(deployment.id),
        extra={"app_slug": app.slug, "image_tag": app.image_tag, "replicas": app.replicas},
    )

    return deployment


@router.post("/deploy-image", response_model=DeploymentResponse, status_code=status.HTTP_202_ACCEPTED)
async def deploy_built_image(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    gitops: GitOpsDep,
    argocd: ArgoCDDep,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    deployment_id: uuid.UUID | None = Query(None, description="Specific BUILT deployment ID. Uses latest if omitted."),
) -> Deployment:
    """Deploy a previously built image (status=BUILT) without rebuilding.

    If deployment_id is omitted, uses the latest BUILT deployment for this app.
    """
    from sqlalchemy import select

    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    app = await _get_app_or_404(tenant.id, app_slug, db)

    if deployment_id:
        deployment = await db.get(Deployment, deployment_id)
        if not deployment or deployment.application_id != app.id:
            raise HTTPException(status_code=404, detail="Deployment not found")
        if deployment.status != DeploymentStatus.BUILT:
            raise HTTPException(
                status_code=409, detail=f"Deployment status is '{deployment.status.value}', expected 'built'"
            )
    else:
        # Find the latest BUILT deployment
        result = await db.execute(
            select(Deployment)
            .where(Deployment.application_id == app.id, Deployment.status == DeploymentStatus.BUILT)
            .order_by(Deployment.created_at.desc())
            .limit(1)
        )
        deployment = result.scalar_one_or_none()
        if not deployment:
            raise HTTPException(
                status_code=404, detail="No BUILT deployment found. Run a build first with deploy=false."
            )

    image_name = deployment.image_tag
    if not image_name:
        raise HTTPException(status_code=409, detail="BUILT deployment has no image_tag")

    # Transition to DEPLOYING and run deploy phase only (reuse redeploy logic)
    deployment.status = DeploymentStatus.DEPLOYING
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
            image=image_name,
            replicas=app.replicas,
            env_vars=dict(app.env_vars),
            service_secret_names=secret_names,
            port=app.port,
            k8s=k8s,
            resource_cpu_request=app.resource_cpu_request,
            resource_cpu_limit=app.resource_cpu_limit,
            resource_memory_request=app.resource_memory_request,
            resource_memory_limit=app.resource_memory_limit,
            health_check_path=app.health_check_path or "",
            custom_domain=app.custom_domain or "",
            min_replicas=app.min_replicas,
            max_replicas=app.max_replicas,
            cpu_threshold=app.cpu_threshold,
            app_type=app.app_type or "web",
        ),
        name=f"deploy-image-{deployment.id}",
    )

    await audit(
        db,
        tenant_id=tenant.id,
        action="deployment.deploy_image",
        user_id=current_user.get("sub", ""),
        resource_type="deployment",
        resource_id=str(deployment.id),
        extra={"app_slug": app.slug, "image_tag": image_name},
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
    current_user: CurrentUser,
) -> Deployment:
    """Roll back to a specific past deployment's image."""
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
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
            resource_cpu_request=app.resource_cpu_request,
            resource_cpu_limit=app.resource_cpu_limit,
            resource_memory_request=app.resource_memory_request,
            resource_memory_limit=app.resource_memory_limit,
            health_check_path=app.health_check_path or "",
            custom_domain=app.custom_domain or "",
            min_replicas=app.min_replicas,
            max_replicas=app.max_replicas,
            cpu_threshold=app.cpu_threshold,
            app_type=app.app_type or "web",
        ),
        name=f"rollback-{rollback_record.id}",
    )
    return rollback_record


class SyncOptions(BaseModel):
    """Options for ArgoCD sync."""

    prune: bool = Field(True, description="Remove resources no longer in git")
    force: bool = Field(False, description="Override immutable field changes")
    dry_run: bool = Field(False, description="Preview only, no actual changes")


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_app(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    argocd: ArgoCDDep,
    current_user: CurrentUser,
    body: SyncOptions | None = None,
) -> dict:
    """Trigger an ArgoCD sync for this application with configurable options."""
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    await _get_app_or_404(tenant.id, app_slug, db)

    app_name = f"{tenant_slug}-{app_slug}"
    opts = body or SyncOptions()
    triggered = await argocd.trigger_sync(
        app_name,
        prune=opts.prune,
        force=opts.force,
        dry_run=opts.dry_run,
    )
    return {"triggered": triggered, "app_name": app_name, "options": opts.model_dump()}


@router.get("/sync-diff")
async def get_sync_diff(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    argocd: ArgoCDDep,
    current_user: CurrentUser,
) -> list[dict]:
    """Get resource diff between live and target state for ArgoCD sync modal."""
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    await _get_app_or_404(tenant.id, app_slug, db)

    app_name = f"{tenant_slug}-{app_slug}"
    return await argocd.get_resource_diff(app_name)


@router.get("/sync-status")
async def get_sync_status(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    argocd: ArgoCDDep,
    current_user: CurrentUser,
) -> dict:
    """Get ArgoCD sync and health status for this application."""
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    await _get_app_or_404(tenant.id, app_slug, db)

    app_name = f"{tenant_slug}-{app_slug}"
    return await argocd.get_app_status(app_name)


@router.get("/deploy-history")
async def get_deploy_history(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    argocd: ArgoCDDep,
    current_user: CurrentUser,
) -> list[dict]:
    """Get ArgoCD deployment history for this application."""
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    await _get_app_or_404(tenant.id, app_slug, db)

    app_name = f"{tenant_slug}-{app_slug}"
    return await argocd.get_app_history(app_name)


@router.post("/rollback/{revision}", status_code=status.HTTP_202_ACCEPTED)
async def argocd_rollback(
    tenant_slug: str,
    app_slug: str,
    revision: int,
    db: DBSession,
    argocd: ArgoCDDep,
    current_user: CurrentUser,
) -> dict:
    """Trigger ArgoCD rollback to a specific history revision ID."""
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    await _get_app_or_404(tenant.id, app_slug, db)

    app_name = f"{tenant_slug}-{app_slug}"
    triggered = await argocd.rollback_app(app_name, revision)
    if not triggered:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="ArgoCD rollback failed")
    return {"triggered": True, "app_name": app_name, "revision": revision}


@router.get("/logs")
async def stream_logs(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
    tail_lines: int = 100,
    pod: str | None = None,
    token: str | None = None,  # noqa: ARG001 — accepted for EventSource auth (validated upstream)
) -> StreamingResponse:
    """Stream pod logs (or build logs if building) via SSE.

    Accepts an optional `token` query param so that browser EventSource
    (which cannot set custom headers) can authenticate.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    app = await _get_app_or_404(tenant.id, app_slug, db)
    namespace = tenant.namespace
    selector = f"app={app.slug}"

    # Preload latest deployment to check for active builds
    result = await db.execute(
        select(Deployment).where(Deployment.application_id == app.id).order_by(Deployment.created_at.desc()).limit(1)
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
                    # Poll for pod to appear (up to 60s) with heartbeats
                    build_pod = None
                    phase = None
                    try:
                        for _wait in range(20):  # 20 * 3s = 60s max
                            build_pods = await asyncio.to_thread(
                                k8s.core_v1.list_namespaced_pod,
                                namespace=settings.build_namespace,
                                label_selector=f"job-name={latest_deployment.build_job_name}",
                            )
                            if build_pods.items:
                                build_pod = build_pods.items[0].metadata.name
                                phase = build_pods.items[0].status.phase
                                break
                            yield "data: [heartbeat]\n\n"
                            yield "data: [waiting for build pod to start...]\n\n"
                            await asyncio.sleep(3)

                        if build_pod and phase:
                            yield f"data: [build pod: {build_pod} ({phase})]\n\n"
                            if phase in ("Running", "Succeeded", "Failed"):
                                # Try each container in order
                                for container in ("git-clone", "nixpacks", "buildctl"):
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
                            yield "data: [build pod did not start within 60s]\n\n"
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

            # Filter by specific pod or stream all replicas
            ready_pods = [
                p
                for p in pods.items
                if p.status.phase in ("Running", "Succeeded", "Failed") and (pod is None or p.metadata.name == pod)
            ]
            if not ready_pods:
                yield "data: [no ready pods found]\n\n"
                yield "data: [end]\n\n"
                return

            multi = len(ready_pods) > 1
            for p in ready_pods:
                pod_name = p.metadata.name
                phase = p.status.phase
                prefix = f"[{pod_name}] " if multi else ""
                yield f"data: {prefix}[pod: {pod_name} ({phase})]\n\n"
                try:
                    logs: str = await asyncio.to_thread(
                        k8s.core_v1.read_namespaced_pod_log,
                        name=pod_name,
                        namespace=namespace,
                        tail_lines=tail_lines,
                    )
                    for line in logs.splitlines():
                        yield f"data: {prefix}{line}\n\n"
                except Exception as exc:  # noqa: BLE001
                    yield f"data: {prefix}[error reading logs: {exc}]\n\n"
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
    # Extended app config
    resource_cpu_request: str = "50m",
    resource_cpu_limit: str = "500m",
    resource_memory_request: str = "64Mi",
    resource_memory_limit: str = "512Mi",
    health_check_path: str = "",
    custom_domain: str = "",
    min_replicas: int = 1,
    max_replicas: int = 5,
    cpu_threshold: int = 70,
    app_type: str = "web",
) -> None:
    """Re-deploy an existing image without going through the build step."""
    from app.models.deployment import Deployment as _Deployment
    from app.services.pipeline import WAIT_FOR_READY_TIMEOUT

    session_factory = get_session_factory()
    deploy_svc = DeployService(k8s)

    async with session_factory() as db:
        dep = await db.get(_Deployment, deployment_id)
        if dep:
            dep.status = DeploymentStatus.DEPLOYING
            await db.commit()

    try:
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
                resource_cpu_request=resource_cpu_request,
                resource_cpu_limit=resource_cpu_limit,
                resource_memory_request=resource_memory_request,
                resource_memory_limit=resource_memory_limit,
                health_check_path=health_check_path,
                custom_domain=custom_domain,
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                cpu_threshold=cpu_threshold,
                app_type=app_type,
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
        try:
            ready, msg = await asyncio.wait_for(
                deploy_svc.wait_for_ready(namespace, app_slug),
                timeout=WAIT_FOR_READY_TIMEOUT,
            )
        except TimeoutError:
            ready, msg = False, f"Readiness check timed out after {WAIT_FOR_READY_TIMEOUT}s"

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
    finally:
        # Safety net: if status is still DEPLOYING after redeploy ends, resolve it
        async with session_factory() as db:
            dep = await db.get(_Deployment, deployment_id)
            if dep and dep.status == DeploymentStatus.DEPLOYING:
                logger.warning(
                    "Deployment %s still in DEPLOYING state after redeploy — checking pod status",
                    deployment_id,
                )
                try:
                    pod_ready, pod_msg = await deploy_svc.wait_for_ready(namespace, app_slug, timeout=10)
                    if pod_ready:
                        dep.status = DeploymentStatus.RUNNING
                        logger.info("Deployment %s resolved to RUNNING via finally check", deployment_id)
                    else:
                        dep.status = DeploymentStatus.FAILED
                        dep.error_message = f"Redeploy ended with DEPLOYING status: {pod_msg}"[:4096]
                        logger.error("Deployment %s resolved to FAILED via finally check: %s", deployment_id, pod_msg)
                except Exception:
                    dep.status = DeploymentStatus.FAILED
                    dep.error_message = "Redeploy ended unexpectedly while still in DEPLOYING status"
                    logger.exception("Deployment %s finally check failed", deployment_id)
                await db.commit()
