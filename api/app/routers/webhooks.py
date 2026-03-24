import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.deps import DBSession, K8sDep
from app.models.application import Application
from app.models.deployment import Deployment, DeploymentStatus

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/github/{webhook_token}", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    webhook_token: str,
    request: Request,
    db: DBSession,
    k8s: K8sDep,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, str]:
    """Receive GitHub push webhook and trigger a build. (skeleton)"""
    # Find application by webhook token (token = sha256(app_id) — stub for now)
    # TODO: store webhook_token on Application model and look it up properly
    result = await db.execute(select(Application).limit(1))  # placeholder
    app = result.scalar_one_or_none()

    if app is None:
        raise HTTPException(status_code=404, detail="No application found for this webhook token")

    payload: dict[str, Any] = await request.json()
    ref: str = payload.get("ref", "")
    commit_sha: str = payload.get("after", "unknown")
    branch = ref.replace("refs/heads/", "")

    if branch != app.branch:
        logger.info("Webhook ignored: branch %s != configured %s", branch, app.branch)
        return {"status": "ignored", "reason": "branch mismatch"}

    # Create deployment record
    deployment = Deployment(
        application_id=app.id,
        commit_sha=commit_sha,
        status=DeploymentStatus.PENDING,
    )
    db.add(deployment)
    await db.commit()

    logger.info("Deployment queued: app=%s commit=%s", app.slug, commit_sha)
    # TODO (Sprint 3): enqueue build job via BuildService

    return {"status": "queued", "deployment_id": str(deployment.id)}
