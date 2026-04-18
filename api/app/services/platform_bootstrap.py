"""Platform-level self-service bootstrap — runs once on iyziops-api startup.

Closes two gaps that were previously done manually during the first cluster
bring-up and broke fresh-cluster reproducibility:

1. Gitea `haven` org + `haven-gitops` repo — every tenant-app deploy clones
   this repo to write values.yaml. Without it, deploys fail with 404.

2. ArgoCD repository Secret for Gitea — ApplicationSets that point at
   haven-gitops need basic-auth credentials to pull. Without the Secret,
   appset-{tenant} reconciles as "authentication required" and no
   Application CRs are created → no K8s Deployment.

Both are idempotent (check-then-create), so running every boot is safe.
Failures are logged and non-fatal — a transient Gitea outage must not
prevent the API from serving requests that don't need GitOps.
"""

from __future__ import annotations

import asyncio
import base64
import logging

from kubernetes.client import ApiException, V1ObjectMeta, V1Secret

from app.config import settings
from app.k8s.client import k8s_client
from app.services.gitea_client import gitea_client

logger = logging.getLogger(__name__)

ARGOCD_NAMESPACE = "argocd"
ARGOCD_GITEA_SECRET_NAME = "gitea-haven-gitops-repo"


async def ensure_haven_gitops_repo() -> None:
    """Ensure Gitea has the `haven` org and `haven-gitops` repo."""
    org = settings.gitea_org
    repo = settings.gitea_gitops_repo
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            await gitea_client.ensure_org(org)
            await gitea_client.ensure_repo(org, repo)
            logger.info("Platform bootstrap: Gitea %s/%s ready", org, repo)
            return
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(2**attempt)
    logger.warning(
        "Platform bootstrap: failed to ensure Gitea %s/%s after 3 attempts — %s",
        org,
        repo,
        last_exc,
    )


def ensure_argocd_gitea_repo_secret() -> None:
    """Ensure ArgoCD has a repository Secret pointing at haven-gitops."""
    token = settings.gitea_admin_token
    if not token:
        logger.warning("Platform bootstrap: GITEA_ADMIN_TOKEN empty — skipping ArgoCD repo secret")
        return
    if not k8s_client.is_available() or k8s_client.core_v1 is None:
        logger.warning("Platform bootstrap: K8s client unavailable — skipping ArgoCD repo secret")
        return

    repo_url = f"{settings.gitea_url.rstrip('/')}/{settings.gitea_org}/{settings.gitea_gitops_repo}.git"
    fields = {
        "type": "git",
        "url": repo_url,
        "username": "gitea_admin",
        "password": token,
    }
    encoded = {k: base64.b64encode(v.encode()).decode() for k, v in fields.items()}
    secret = V1Secret(
        api_version="v1",
        kind="Secret",
        metadata=V1ObjectMeta(
            name=ARGOCD_GITEA_SECRET_NAME,
            namespace=ARGOCD_NAMESPACE,
            labels={
                "argocd.argoproj.io/secret-type": "repository",
                "haven.io/managed": "true",
            },
        ),
        data=encoded,
        type="Opaque",
    )

    try:
        k8s_client.core_v1.create_namespaced_secret(ARGOCD_NAMESPACE, secret)
        logger.info("Platform bootstrap: created ArgoCD repo Secret %s", ARGOCD_GITEA_SECRET_NAME)
        return
    except ApiException as exc:
        if exc.status != 409:
            logger.warning("Platform bootstrap: create ArgoCD secret failed — %s", exc)
            return

    try:
        k8s_client.core_v1.replace_namespaced_secret(ARGOCD_GITEA_SECRET_NAME, ARGOCD_NAMESPACE, secret)
        logger.info("Platform bootstrap: updated ArgoCD repo Secret %s", ARGOCD_GITEA_SECRET_NAME)
    except ApiException as exc:
        logger.warning("Platform bootstrap: replace ArgoCD secret failed — %s", exc)


async def run_platform_bootstrap() -> None:
    """Run both bootstrap steps. Non-fatal on any single failure."""
    await ensure_haven_gitops_repo()
    try:
        ensure_argocd_gitea_repo_secret()
    except Exception:
        logger.exception("Platform bootstrap: ArgoCD secret step raised")
