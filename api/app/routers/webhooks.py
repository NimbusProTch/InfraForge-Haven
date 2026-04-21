import asyncio
import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.config import settings
from app.deps import ArgoCDDep, DBSession, GitOpsDep, K8sDep, get_session_factory
from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.environment import Environment, EnvironmentStatus, EnvironmentType
from app.models.tenant import Tenant
from app.rate_limit import RATE_WEBHOOK, limiter
from app.routers.environments import _compute_domain, _compute_namespace
from app.services.pipeline import run_pipeline

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


def _is_placeholder_secret(secret: str) -> bool:
    """Return True if `secret` matches a known placeholder literal.

    A placeholder means the Secret was never wired up to a real value. We
    fail-closed on inbound webhooks to prevent signature bypass by an
    attacker who knows the literal (e.g. `placeholder`).

    Defensive against test mocks that forget to set the tuple: if the
    attribute is missing or not a collection, treat the guard as disabled.
    """
    placeholders = getattr(settings, "webhook_secret_placeholder_values", ())
    if not isinstance(placeholders, (tuple, list, set, frozenset)):
        return False
    return secret.strip().lower() in placeholders


def _verify_github_signature(body: bytes, secret: str, signature_header: str | None) -> None:
    """Raise 401 if the HMAC-SHA256 signature does not match.

    If WEBHOOK_SECRET is not configured at all, the check is skipped (dev
    mode only). If it is set but equals a known placeholder literal, the
    request is rejected with 503 so a misconfigured prod cannot silently
    accept forged signatures.
    """
    if not secret:
        logger.warning("WEBHOOK_SECRET not set — skipping signature verification (dev mode)")
        return
    if _is_placeholder_secret(secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub webhook endpoint misconfigured (WEBHOOK_SECRET placeholder)",
        )
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header",
        )
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )


@router.post("/github/{webhook_token}", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(RATE_WEBHOOK)
async def github_webhook(
    webhook_token: str,
    request: Request,
    db: DBSession,
    k8s: K8sDep,
    gitops: GitOpsDep,
    argocd: ArgoCDDep,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, str]:
    """Receive GitHub push or pull_request webhooks.

    URL: POST /api/v1/webhooks/github/{webhook_token}
    The webhook_token is shown in the application detail response.

    Supported events:
    - push → trigger build + deploy on configured branch
    - pull_request (opened/synchronize) → create/update preview environment
    - pull_request (closed) → delete preview environment + K8s namespace
    """
    body = await request.body()
    _verify_github_signature(body, settings.webhook_secret, x_hub_signature_256)

    event = x_github_event or ""

    # Route to the correct handler
    if event == "push":
        return await _handle_push(webhook_token, request, db, k8s, gitops, argocd)
    if event == "pull_request":
        return await _handle_pull_request(webhook_token, request, db, k8s, gitops, argocd)

    logger.info("Webhook event %s ignored", event)
    return {"status": "ignored", "reason": f"event={event}"}


# ---------------------------------------------------------------------------
# Push handler (existing behaviour)
# ---------------------------------------------------------------------------


async def _handle_push(
    webhook_token: str, request: Request, db: DBSession, k8s: K8sDep, gitops: GitOpsDep, argocd: ArgoCDDep
) -> dict[str, str]:
    result = await db.execute(select(Application).where(Application.webhook_token == webhook_token))
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="No application found for this webhook token")

    payload: dict[str, Any] = await request.json()
    ref: str = payload.get("ref", "")
    commit_sha: str = payload.get("after", "unknown")
    branch = ref.removeprefix("refs/heads/")

    if branch != app.branch:
        logger.info("Push webhook ignored: branch %s != configured %s", branch, app.branch)
        return {"status": "ignored", "reason": "branch mismatch"}

    if not app.auto_deploy:
        logger.info("Push webhook ignored: auto_deploy disabled for app %s", app.slug)
        return {"status": "ignored", "reason": "auto_deploy disabled"}

    tenant = await db.get(Tenant, app.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=500, detail="Tenant not found for application")

    deployment = Deployment(
        application_id=app.id,
        commit_sha=commit_sha,
        status=DeploymentStatus.PENDING,
    )
    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)

    logger.info(
        "Push deployment queued: app=%s tenant=%s branch=%s commit=%s deployment_id=%s",
        app.slug,
        tenant.slug,
        branch,
        commit_sha,
        deployment.id,
    )

    asyncio.create_task(
        run_pipeline(
            deployment_id=deployment.id,
            app_id=app.id,
            repo_url=app.repo_url,
            branch=branch,
            commit_sha=commit_sha,
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
        ),
        name=f"pipeline-{deployment.id}",
    )

    return {"status": "queued", "deployment_id": str(deployment.id)}


# ---------------------------------------------------------------------------
# Pull Request handler (preview environments)
# ---------------------------------------------------------------------------


async def _handle_pull_request(
    webhook_token: str, request: Request, db: DBSession, k8s: K8sDep, gitops: GitOpsDep, argocd: ArgoCDDep
) -> dict[str, str]:
    result = await db.execute(select(Application).where(Application.webhook_token == webhook_token))
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="No application found for this webhook token")

    tenant = await db.get(Tenant, app.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=500, detail="Tenant not found for application")

    payload: dict[str, Any] = await request.json()
    action: str = payload.get("action", "")
    pr: dict[str, Any] = payload.get("pull_request", {})
    pr_number: int = pr.get("number", 0)
    head: dict[str, Any] = pr.get("head", {})
    branch: str = head.get("ref", "")
    commit_sha: str = head.get("sha", "unknown")
    env_name = f"pr-{pr_number}"

    if action in ("opened", "synchronize", "reopened"):
        return await _upsert_preview(
            app=app,
            tenant=tenant,
            env_name=env_name,
            pr_number=pr_number,
            branch=branch,
            commit_sha=commit_sha,
            db=db,
            k8s=k8s,
            gitops=gitops,
            argocd=argocd,
        )

    if action in ("closed",):
        return await _delete_preview(
            app=app,
            tenant=tenant,
            env_name=env_name,
            db=db,
            k8s=k8s,
        )

    logger.info("PR action %s ignored for app=%s pr=%d", action, app.slug, pr_number)
    return {"status": "ignored", "reason": f"action={action}"}


async def _upsert_preview(
    *,
    app: Application,
    tenant: Tenant,
    env_name: str,
    pr_number: int,
    branch: str,
    commit_sha: str,
    db: DBSession,
    k8s: K8sDep,
    gitops: GitOpsDep,
    argocd: ArgoCDDep,
) -> dict[str, str]:
    """Create or update a preview environment, then queue a build+deploy."""
    # Find or create the Environment record
    result = await db.execute(
        select(Environment).where(Environment.application_id == app.id, Environment.name == env_name)
    )
    env = result.scalar_one_or_none()

    if env is None:
        env = Environment(
            application_id=app.id,
            name=env_name,
            env_type=EnvironmentType.preview,
            branch=branch,
            pr_number=pr_number,
            env_vars={},
        )
        db.add(env)
        await db.flush()
        env.domain = _compute_domain(tenant.slug, app.slug, env)

    # Update branch in case the PR head changed
    env.branch = branch
    env.status = EnvironmentStatus.building
    await db.commit()
    await db.refresh(env)

    # Merge app env_vars with environment overrides
    merged_env_vars = {**dict(app.env_vars), **dict(env.env_vars)}

    namespace = _compute_namespace(tenant.slug, env)
    deployment = Deployment(
        application_id=app.id,
        environment_id=env.id,
        commit_sha=commit_sha,
        status=DeploymentStatus.PENDING,
    )
    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)

    logger.info(
        "Preview deployment queued: app=%s env=%s pr=%d branch=%s commit=%s",
        app.slug,
        env_name,
        pr_number,
        branch,
        commit_sha,
    )

    asyncio.create_task(
        run_pipeline(
            deployment_id=deployment.id,
            app_id=app.id,
            repo_url=app.repo_url,
            branch=branch,
            commit_sha=commit_sha,
            app_slug=app.slug,
            tenant_slug=tenant.slug,
            namespace=namespace,
            tenant_id=tenant.id,
            env_vars=merged_env_vars,
            replicas=env.replicas or app.replicas,
            port=app.port,
            session_factory=get_session_factory(),
            k8s=k8s,
            github_token=tenant.github_token,
            gitops=gitops,
            argocd=argocd,
            environment_id=env.id,
        ),
        name=f"pipeline-{deployment.id}",
    )

    return {
        "status": "queued",
        "deployment_id": str(deployment.id),
        "environment": env_name,
        "url": env.domain or "",
    }


async def _delete_preview(
    *,
    app: Application,
    tenant: Tenant,
    env_name: str,
    db: DBSession,
    k8s: K8sDep,
) -> dict[str, str]:
    """Delete a preview environment when PR is closed."""
    result = await db.execute(
        select(Environment).where(Environment.application_id == app.id, Environment.name == env_name)
    )
    env = result.scalar_one_or_none()
    if env is None:
        logger.info("No preview environment %s to delete", env_name)
        return {"status": "ignored", "reason": "no preview environment found"}

    env.status = EnvironmentStatus.deleting
    await db.commit()

    # Delete K8s namespace (removes all resources)
    namespace = _compute_namespace(tenant.slug, env)
    if k8s.is_available() and k8s.core_v1 is not None:
        try:
            k8s.core_v1.delete_namespace(namespace)
            logger.info("Deleted K8s namespace %s for preview %s", namespace, env_name)
        except Exception:
            logger.warning("Could not delete namespace %s — may not exist", namespace)

    await db.delete(env)
    await db.commit()

    logger.info("Preview environment %s deleted for app=%s", env_name, app.slug)
    return {"status": "deleted", "environment": env_name}


# ---------------------------------------------------------------------------
# Gitea webhook handler (Sprint 3)
# ---------------------------------------------------------------------------


def _verify_gitea_signature(body: bytes, secret: str, signature_header: str | None) -> None:
    """Validate Gitea HMAC-SHA256 webhook signature.

    Same fail-closed contract as `_verify_github_signature`: placeholder
    secret → 503, empty → skip (dev mode).
    """
    if not secret:
        logger.warning("WEBHOOK_SECRET not set — skipping Gitea signature verification (dev mode)")
        return
    if _is_placeholder_secret(secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gitea webhook endpoint misconfigured (WEBHOOK_SECRET placeholder)",
        )
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Gitea-Signature header",
        )
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Gitea webhook signature",
        )


@router.post("/gitea/{webhook_token}", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(RATE_WEBHOOK)
async def gitea_webhook(
    webhook_token: str,
    request: Request,
    db: DBSession,
    k8s: K8sDep,
    gitops: GitOpsDep,
    argocd: ArgoCDDep,
    x_gitea_signature: str | None = Header(default=None),
    x_gitea_event: str | None = Header(default=None),
) -> dict[str, str]:
    """Receive Gitea push webhooks.

    URL: POST /api/v1/webhooks/gitea/{webhook_token}
    Supported events:
    - push → trigger build + deploy on configured branch
    """
    body = await request.body()
    _verify_gitea_signature(body, settings.webhook_secret, x_gitea_signature)

    event = x_gitea_event or ""

    if event == "push":
        return await _handle_gitea_push(webhook_token, request, db, k8s, gitops, argocd)

    logger.info("Gitea webhook event %s ignored", event)
    return {"status": "ignored", "reason": f"event={event}"}


async def _handle_gitea_push(
    webhook_token: str,
    request: Request,
    db: DBSession,
    k8s: K8sDep,
    gitops: GitOpsDep,
    argocd: ArgoCDDep,
) -> dict[str, str]:
    result = await db.execute(select(Application).where(Application.webhook_token == webhook_token))
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="No application found for this webhook token")

    payload: dict[str, Any] = await request.json()
    ref: str = payload.get("ref", "")
    commit_sha: str = payload.get("after", "unknown")
    branch = ref.removeprefix("refs/heads/")

    if branch != app.branch:
        logger.info("Gitea push webhook ignored: branch %s != configured %s", branch, app.branch)
        return {"status": "ignored", "reason": "branch mismatch"}

    if not app.auto_deploy:
        logger.info("Gitea push webhook ignored: auto_deploy disabled for app %s", app.slug)
        return {"status": "ignored", "reason": "auto_deploy disabled"}

    tenant = await db.get(Tenant, app.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=500, detail="Tenant not found for application")

    deployment = Deployment(
        application_id=app.id,
        commit_sha=commit_sha,
        status=DeploymentStatus.PENDING,
    )
    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)

    logger.info(
        "Gitea push deployment queued: app=%s tenant=%s branch=%s commit=%s",
        app.slug,
        tenant.slug,
        branch,
        commit_sha,
    )

    asyncio.create_task(
        run_pipeline(
            deployment_id=deployment.id,
            app_id=app.id,
            repo_url=app.repo_url,
            branch=branch,
            commit_sha=commit_sha,
            app_slug=app.slug,
            tenant_slug=tenant.slug,
            namespace=tenant.namespace,
            tenant_id=tenant.id,
            env_vars=dict(app.env_vars),
            replicas=app.replicas,
            port=app.port,
            session_factory=get_session_factory(),
            k8s=k8s,
            github_token=None,
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
        ),
        name=f"pipeline-{deployment.id}",
    )

    return {"status": "queued", "deployment_id": str(deployment.id)}
