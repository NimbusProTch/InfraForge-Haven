import asyncio
import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.config import settings
from app.deps import DBSession, K8sDep, get_session_factory
from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus
from app.models.tenant import Tenant
from app.services.pipeline import run_pipeline

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


def _verify_github_signature(body: bytes, secret: str, signature_header: str | None) -> None:
    """Raise 401 if the HMAC-SHA256 signature does not match.

    If WEBHOOK_SECRET is not configured the check is skipped (dev mode only).
    """
    if not secret:
        logger.warning("WEBHOOK_SECRET not set — skipping signature verification (dev mode)")
        return
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
async def github_webhook(
    webhook_token: str,
    request: Request,
    db: DBSession,
    k8s: K8sDep,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, str]:
    """Receive a GitHub push webhook and trigger a build.

    URL: POST /api/v1/webhooks/github/{webhook_token}
    The webhook_token is shown in the application detail response.
    Configure it as the GitHub webhook secret payload URL.
    """
    body = await request.body()
    _verify_github_signature(body, settings.webhook_secret, x_hub_signature_256)

    # Ignore non-push events (ping, etc.)
    if x_github_event and x_github_event != "push":
        logger.info("Webhook event %s ignored (not a push)", x_github_event)
        return {"status": "ignored", "reason": f"event={x_github_event}"}

    # Look up application by webhook token
    result = await db.execute(
        select(Application).where(Application.webhook_token == webhook_token)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="No application found for this webhook token")

    payload: dict[str, Any] = await request.json()
    ref: str = payload.get("ref", "")
    commit_sha: str = payload.get("after", "unknown")
    branch = ref.removeprefix("refs/heads/")

    if branch != app.branch:
        logger.info("Webhook ignored: branch %s != configured %s", branch, app.branch)
        return {"status": "ignored", "reason": "branch mismatch"}

    # Load tenant for namespace + slug
    tenant = await db.get(Tenant, app.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=500, detail="Tenant not found for application")

    # Create deployment record
    deployment = Deployment(
        application_id=app.id,
        commit_sha=commit_sha,
        status=DeploymentStatus.PENDING,
    )
    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)

    logger.info(
        "Deployment queued: app=%s tenant=%s branch=%s commit=%s deployment_id=%s",
        app.slug,
        tenant.slug,
        branch,
        commit_sha,
        deployment.id,
    )

    session_factory = get_session_factory()

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
            session_factory=session_factory,
            k8s=k8s,
        ),
        name=f"pipeline-{deployment.id}",
    )

    return {"status": "queued", "deployment_id": str(deployment.id)}
