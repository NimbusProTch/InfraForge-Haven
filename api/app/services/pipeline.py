"""Build + deploy pipeline orchestration.

Runs as a background asyncio task so the webhook handler can return 202
immediately while the pipeline runs asynchronously.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.k8s.client import K8sClient
from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.services.build_service import BuildService
from app.services.deploy_service import DeployService, get_service_secret_names

logger = logging.getLogger(__name__)


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
    session_factory: async_sessionmaker[AsyncSession],
    k8s: K8sClient,
) -> None:
    """Run full build → deploy pipeline, persisting status to DB at each step."""
    harbor_host = settings.harbor_url.removeprefix("https://").removeprefix("http://")
    image_name = (
        f"{harbor_host}/{settings.harbor_project}/{namespace}/{app_slug}:{commit_sha[:8]}"
    )
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
        )
    except Exception as exc:
        logger.exception("Failed to submit build job for deployment %s", deployment_id)
        await _fail(deployment_id, str(exc), session_factory)
        return

    async with session_factory() as db:
        deployment = await db.get(Deployment, deployment_id)
        if deployment:
            deployment.build_job_name = job_name
            await db.commit()

    # --- WAIT FOR BUILD -------------------------------------------------
    final_build_status = await build_svc.wait_for_completion(settings.build_namespace, job_name)

    if final_build_status != "succeeded":
        logs = await build_svc.get_build_logs(settings.build_namespace, job_name)
        error_msg = f"Build job {job_name} finished with status={final_build_status}"
        if logs:
            error_msg += f"\n\n--- Kaniko logs ---\n{logs[-2000:]}"
        logger.error(error_msg)
        await _fail(deployment_id, error_msg, session_factory)
        return

    # --- DEPLOYING ------------------------------------------------------
    async with session_factory() as db:
        deployment = await db.get(Deployment, deployment_id)
        if deployment:
            deployment.status = DeploymentStatus.DEPLOYING
            deployment.image_tag = image_name
            await db.commit()

        # Collect managed service secrets to inject into the app
        secret_names = await get_service_secret_names(db, tenant_id)

    try:
        await deploy_svc.deploy(
            namespace=namespace,
            tenant_slug=tenant_slug,
            app_slug=app_slug,
            image=image_name,
            replicas=replicas,
            env_vars=env_vars,
            service_secret_names=secret_names,
        )
    except Exception as exc:
        logger.exception("Deploy failed for deployment %s", deployment_id)
        await _fail(deployment_id, str(exc), session_factory)
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

    logger.info(
        "Pipeline complete: deployment=%s image=%s namespace=%s app=%s",
        deployment_id,
        image_name,
        namespace,
        app_slug,
    )


async def _fail(
    deployment_id: uuid.UUID,
    error_message: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        deployment = await db.get(Deployment, deployment_id)
        if deployment:
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = error_message[:4096]
            await db.commit()
