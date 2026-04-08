"""Build + deploy pipeline orchestration.

Runs as a background asyncio task so the webhook handler can return 202
immediately while the pipeline runs asynchronously.

Supports two deployment modes:
  1. GitOps: writes Helm values to git → ArgoCD syncs (preferred)
  2. Direct: calls K8s API directly (fallback when GitOps not configured)
"""

import asyncio
import logging
import uuid

import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.k8s.client import K8sClient
from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.environment import Environment, EnvironmentStatus
from app.services.argocd_service import ArgoCDService
from app.services.build_service import BuildService
from app.services.deploy_service import DeployService, get_service_secret_names
from app.services.git_queue_service import GitOperation, GitQueueService
from app.services.gitops_service import GitOpsService
from app.services.helm_values_builder import build_app_values

# Maximum time (seconds) to wait for a deployment to become ready
WAIT_FOR_READY_TIMEOUT = 180

logger = logging.getLogger(__name__)


def _use_gitops() -> bool:
    """Check if GitOps mode is available (gitops repo URL configured)."""
    return bool(settings.gitops_repo_url)


async def run_pipeline(
    *,
    deployment_id: uuid.UUID,
    app_id: uuid.UUID,
    repo_url: str,
    branch: str,
    commit_sha: str,
    app_slug: str,
    tenant_slug: str,
    namespace: str,
    tenant_id: uuid.UUID,
    env_vars: dict[str, str],
    replicas: int,
    port: int,
    session_factory: async_sessionmaker[AsyncSession],
    k8s: K8sClient,
    github_token: str | None = None,
    gitops: GitOpsService | None = None,
    argocd: ArgoCDService | None = None,
    queue: GitQueueService | None = None,
    # Extended app config
    custom_domain: str = "",
    health_check_path: str = "",
    resource_cpu_request: str = "50m",
    resource_cpu_limit: str = "500m",
    resource_memory_request: str = "64Mi",
    resource_memory_limit: str = "512Mi",
    min_replicas: int = 1,
    max_replicas: int = 5,
    cpu_threshold: int = 70,
    app_type: str = "web",
    # Monorepo support
    dockerfile_path: str | None = None,
    build_context: str | None = None,
    use_dockerfile: bool = False,
    # Optional: environment context (staging/preview)
    environment_id: uuid.UUID | None = None,
    # Build-only mode: if False, stops after successful build (BUILT status)
    deploy: bool = True,
) -> None:
    """Run build → deploy pipeline, persisting status to DB at each step.

    When deploy=False, stops after a successful build and sets status to BUILT.
    The image is pushed to Harbor but not deployed to K8s.
    """
    harbor_host = settings.harbor_url.removeprefix("https://").removeprefix("http://")
    image_name = f"{harbor_host}/{settings.harbor_project}/{namespace}/{app_slug}:{commit_sha[:8]}"
    build_svc = BuildService(k8s)
    deploy_svc = DeployService(k8s)

    # --- BUILDING -------------------------------------------------------
    async with session_factory() as db:
        deployment = await db.get(Deployment, deployment_id)
        if deployment is None:
            logger.error("Deployment %s not found, aborting pipeline", deployment_id)
            return
        deployment.status = DeploymentStatus.BUILDING
        await db.commit()

    job_name: str | None = None
    try:
        job_name = await build_svc.trigger_build(
            namespace=settings.build_namespace,
            app_slug=app_slug,
            repo_url=repo_url,
            branch=branch,
            commit_sha=commit_sha,
            image_name=image_name,
            github_token=github_token,
            dockerfile_path=dockerfile_path,
            build_context=build_context,
            use_dockerfile=use_dockerfile,
        )
    except Exception as exc:
        logger.exception("Failed to submit build job for deployment %s", deployment_id)
        await _fail(deployment_id, str(exc), session_factory, environment_id)
        return

    async with session_factory() as db:
        deployment = await db.get(Deployment, deployment_id)
        if deployment:
            deployment.build_job_name = job_name
            await db.commit()

    # --- WAIT FOR BUILD -------------------------------------------------
    final_build_status = await build_svc.wait_for_completion(settings.build_namespace, job_name)

    if final_build_status != "succeeded":
        all_logs = await build_svc.get_build_logs(settings.build_namespace, job_name)
        error_msg = f"Build job {job_name} finished with status={final_build_status}"
        if all_logs:
            error_msg += f"\n\n{all_logs[-3000:]}"
        logger.error(error_msg)
        await _fail(deployment_id, error_msg, session_factory, environment_id)
        return

    # --- BUILD-ONLY MODE ------------------------------------------------
    if not deploy:
        async with session_factory() as db:
            deployment = await db.get(Deployment, deployment_id)
            if deployment:
                deployment.status = DeploymentStatus.BUILT
                deployment.image_tag = image_name
                await db.commit()

            app = await db.get(Application, app_id)
            if app:
                app.image_tag = image_name
                await db.commit()

        logger.info(
            "Build-only pipeline complete: deployment=%s image=%s app=%s",
            deployment_id,
            image_name,
            app_slug,
        )
        return

    # --- DEPLOYING ------------------------------------------------------
    async with session_factory() as db:
        deployment = await db.get(Deployment, deployment_id)
        if deployment:
            deployment.status = DeploymentStatus.DEPLOYING
            deployment.image_tag = image_name
            await db.commit()

        secret_names = await get_service_secret_names(db, tenant_id)

    # Always include app-level env secret (Vault or K8s Secret for sensitive vars)
    app_env_secret = f"{app_slug}-env-secrets"
    if app_env_secret not in secret_names:
        secret_names.append(app_env_secret)

    # Choose deployment mode: GitOps or Direct K8s API
    use_gitops = _use_gitops() and gitops is not None

    try:
        if use_gitops:
            # GitOps mode: write values to git → ArgoCD syncs
            values = build_app_values(
                tenant_slug=tenant_slug,
                app_slug=app_slug,
                namespace=namespace,
                image=image_name,
                replicas=replicas,
                env_vars=env_vars,
                service_secret_names=secret_names,
                port=port,
                custom_domain=custom_domain,
                health_check_path=health_check_path,
                resource_cpu_request=resource_cpu_request,
                resource_cpu_limit=resource_cpu_limit,
                resource_memory_request=resource_memory_request,
                resource_memory_limit=resource_memory_limit,
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                cpu_threshold=cpu_threshold,
            )
            gitops_sha = await gitops.write_app_values(tenant_slug, app_slug, values)

            # Store gitops commit SHA
            async with session_factory() as db:
                deployment = await db.get(Deployment, deployment_id)
                if deployment and hasattr(deployment, "gitops_commit_sha"):
                    deployment.gitops_commit_sha = gitops_sha
                    await db.commit()

            # Trigger ArgoCD sync for faster feedback
            if argocd:
                await argocd.trigger_sync(f"{tenant_slug}-{app_slug}")

        else:
            # Direct K8s API mode (fallback)
            await deploy_svc.deploy(
                namespace=namespace,
                tenant_slug=tenant_slug,
                app_slug=app_slug,
                image=image_name,
                replicas=replicas,
                env_vars=env_vars,
                service_secret_names=secret_names,
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
        logger.exception("Deploy failed for deployment %s", deployment_id)
        await _fail(deployment_id, str(exc), session_factory, environment_id)
        return

    # --- WAIT FOR READY -------------------------------------------------
    try:
        if use_gitops and argocd:
            # Trigger immediate sync (instead of waiting for ArgoCD's polling interval)
            argocd_app_name = f"{tenant_slug}-{app_slug}"
            try:
                synced = await argocd.trigger_sync(argocd_app_name, prune=False)
                logger.info("ArgoCD sync triggered for %s: %s", argocd_app_name, synced)
            except Exception as sync_exc:
                logger.warning("Failed to trigger ArgoCD sync: %s", sync_exc)

            # Wait for ArgoCD to sync and report healthy
            try:
                ready, msg = await asyncio.wait_for(
                    argocd.wait_for_healthy(argocd_app_name),
                    timeout=WAIT_FOR_READY_TIMEOUT,
                )
            except TimeoutError:
                ready, msg = False, f"ArgoCD wait timed out after {WAIT_FOR_READY_TIMEOUT}s"
            if not ready:
                # Fallback: ArgoCD may be unreachable but pod might be running via auto-sync
                logger.warning("ArgoCD wait failed (%s) — falling back to K8s check", msg)
                try:
                    ready, msg = await asyncio.wait_for(
                        deploy_svc.wait_for_ready(namespace, app_slug, timeout=120),
                        timeout=120,
                    )
                except TimeoutError:
                    ready, msg = False, "K8s readiness check timed out after 120s"
        else:
            # Direct K8s mode: wait for deployment ready replicas
            try:
                ready, msg = await asyncio.wait_for(
                    deploy_svc.wait_for_ready(namespace, app_slug),
                    timeout=WAIT_FOR_READY_TIMEOUT,
                )
            except TimeoutError:
                ready, msg = False, f"K8s readiness check timed out after {WAIT_FOR_READY_TIMEOUT}s"

        if not ready:
            logger.error("Deployment not ready: %s (deployment=%s)", msg, deployment_id)
            await _fail(deployment_id, msg, session_factory, environment_id)
            return

        # --- RUNNING --------------------------------------------------------
        async with session_factory() as db:
            deployment = await db.get(Deployment, deployment_id)
            if deployment:
                deployment.status = DeploymentStatus.RUNNING
                await db.commit()

            app = await db.get(Application, app_id)
            if app:
                app.image_tag = image_name
                await db.commit()

            # Update environment status if this is a scoped deployment
            if environment_id is not None:
                env = await db.get(Environment, environment_id)
                if env:
                    env.status = EnvironmentStatus.running
                    env.last_image_tag = image_name
                    await db.commit()

        # Enqueue image tag update via git queue to keep gitops repo in sync
        if queue is not None:
            try:
                values = build_app_values(
                    tenant_slug=tenant_slug,
                    app_slug=app_slug,
                    namespace=namespace,
                    image=image_name,
                    replicas=replicas,
                    env_vars=env_vars,
                    service_secret_names=list(secret_names),
                    port=port,
                    custom_domain=custom_domain,
                    health_check_path=health_check_path,
                    resource_cpu_request=resource_cpu_request,
                    resource_cpu_limit=resource_cpu_limit,
                    resource_memory_request=resource_memory_request,
                    resource_memory_limit=resource_memory_limit,
                    min_replicas=min_replicas,
                    max_replicas=max_replicas,
                    cpu_threshold=cpu_threshold,
                )
                await queue.enqueue(
                    GitOperation.UPDATE_FILE,
                    {
                        "tenant_slug": tenant_slug,
                        "app_slug": app_slug,
                        "values": values,
                        "repo": settings.gitea_gitops_repo,
                        "path": f"tenants/{tenant_slug}/{app_slug}/values.yaml",
                        "commit_message": f"[haven] deploy {tenant_slug}/{app_slug} image={commit_sha[:8]}",
                        "author": "Haven Platform <haven@haven.dev>",
                        "content": yaml.dump(values, default_flow_style=False, sort_keys=False),
                    },
                )
                logger.info("Enqueued image tag update for %s/%s", tenant_slug, app_slug)
            except Exception:
                logger.exception("Failed to enqueue image tag update for %s/%s", tenant_slug, app_slug)

        logger.info(
            "Pipeline complete: deployment=%s image=%s namespace=%s app=%s mode=%s",
            deployment_id,
            image_name,
            namespace,
            app_slug,
            "gitops" if use_gitops else "direct",
        )
    finally:
        # Safety net: if status is still DEPLOYING after pipeline ends, resolve it
        async with session_factory() as db:
            deployment = await db.get(Deployment, deployment_id)
            if deployment and deployment.status == DeploymentStatus.DEPLOYING:
                logger.warning(
                    "Deployment %s still in DEPLOYING state after pipeline — checking pod status",
                    deployment_id,
                )
                try:
                    pod_ready, pod_msg = await deploy_svc.wait_for_ready(namespace, app_slug, timeout=10)
                    if pod_ready:
                        deployment.status = DeploymentStatus.RUNNING
                        logger.info("Deployment %s resolved to RUNNING via finally check", deployment_id)
                    else:
                        deployment.status = DeploymentStatus.FAILED
                        deployment.error_message = f"Pipeline ended with DEPLOYING status: {pod_msg}"[:4096]
                        logger.error("Deployment %s resolved to FAILED via finally check: %s", deployment_id, pod_msg)
                except Exception:
                    deployment.status = DeploymentStatus.FAILED
                    deployment.error_message = "Pipeline ended unexpectedly while still in DEPLOYING status"
                    logger.exception("Deployment %s finally check failed", deployment_id)
                await db.commit()


async def _fail(
    deployment_id: uuid.UUID,
    error_message: str,
    session_factory: async_sessionmaker[AsyncSession],
    environment_id: uuid.UUID | None = None,
) -> None:
    async with session_factory() as db:
        deployment = await db.get(Deployment, deployment_id)
        if deployment:
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = error_message[:4096]
            await db.commit()

        if environment_id is not None:
            env = await db.get(Environment, environment_id)
            if env:
                env.status = EnvironmentStatus.failed
                await db.commit()
