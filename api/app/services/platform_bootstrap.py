"""Platform-level self-service bootstrap — runs once on iyziops-api startup.

Closes three gaps that were previously done manually during the first cluster
bring-up and broke fresh-cluster reproducibility:

1. Gitea `haven` org + `haven-gitops` repo — every tenant-app deploy clones
   this repo to write values.yaml. Without it, deploys fail with 404.

2. ArgoCD repository Secret for Gitea — ApplicationSets that point at
   haven-gitops need basic-auth credentials to pull. Without the Secret,
   appset-{tenant} reconciles as "authentication required" and no
   Application CRs are created → no K8s Deployment.

3. ArgoCD `iyziops-api` local account + persistent API token — the deploy
   pipeline polls ArgoCD Application status to know when a sync finishes.
   Without an auth token every call returns 401, the pipeline times out
   after 180s, falls back to a 120s K8s readiness check, and stamps the
   deployment FAILED even when the pod is actually Running. The bootstrap
   provisions a dedicated local account (NOT admin), grants it
   `applications, get/sync/*` RBAC, mints a no-expiration token via
   `/api/v1/account/iyziops-api/token`, and writes it to the
   `iyziops-argocd-token` Secret in haven-system.

All steps are idempotent (check-then-create), so running every boot is safe.
Failures are logged and non-fatal — a transient outage of any of these
dependencies must not prevent the API from serving requests that don't need
the failing dependency.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets
from datetime import UTC, datetime

import bcrypt
import httpx
from kubernetes.client import ApiException, V1ObjectMeta, V1Secret

from app.config import settings
from app.k8s.client import k8s_client
from app.services.gitea_client import gitea_client

logger = logging.getLogger(__name__)

ARGOCD_NAMESPACE = "argocd"
ARGOCD_GITEA_SECRET_NAME = "gitea-haven-gitops-repo"
ARGOCD_TOKEN_SECRET_NAME = "iyziops-argocd-token"  # noqa: S105
ARGOCD_TOKEN_SECRET_NAMESPACE = "haven-system"
ARGOCD_LOCAL_ACCOUNT = "iyziops-api"
ARGOCD_CM_NAME = "argocd-cm"
ARGOCD_SECRET_NAME = "argocd-secret"  # noqa: S105
ARGOCD_RBAC_CM_NAME = "argocd-rbac-cm"


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


# ---------------------------------------------------------------------------
# ArgoCD `iyziops-api` local account + persistent API token bootstrap
# ---------------------------------------------------------------------------
#
# Flow on every iyziops-api boot:
#   0. If `iyziops-argocd-token` Secret already has a non-empty `token`,
#      return early (idempotent — the bootstrap only needs to mint once).
#   1. Patch `argocd-cm` to add `accounts.iyziops-api: apiKey,login`.
#      (apiKey = mint tokens; login = use password for token-mint call)
#   2. Generate a random 32-byte password, bcrypt it, patch `argocd-secret`
#      with `accounts.iyziops-api.password` + `.passwordMtime`.
#   3. Patch `argocd-rbac-cm` policy.csv to grant role:iyziops-api the
#      `applications, get/sync/*` permissions and bind the user to it.
#   4. Sleep briefly for ArgoCD's in-process informer to reload.
#   5. Login via POST /api/v1/session → JWT.
#   6. Mint persistent token via POST /api/v1/account/iyziops-api/token.
#   7. Write the persistent token to Secret `iyziops-argocd-token`
#      in haven-system namespace.
#
# Admin password is NOT touched — this keeps the operator's UI/CLI access
# intact and lets the platform mint its own scoped credential.

ARGOCD_RBAC_LINES = [
    "p, role:iyziops-api, applications, get, */*, allow",
    "p, role:iyziops-api, applications, sync, */*, allow",
    "p, role:iyziops-api, applications, action/*, */*, allow",
    "g, iyziops-api, role:iyziops-api",
]


def _read_existing_argocd_token() -> str | None:
    """Return current token from iyziops-argocd-token Secret, or None if absent/empty."""
    if k8s_client.core_v1 is None:
        return None
    try:
        # NOTE: read_namespaced_secret signature is (name, namespace) — getting the
        # order wrong silently returns 404 every time, defeating the short-circuit
        # and re-running the password-rotation on every pod boot, which races and
        # invalidates previously-minted tokens. This bug shipped in the initial
        # PR #149 commit and was caught during post-merge verification.
        s = k8s_client.core_v1.read_namespaced_secret(ARGOCD_TOKEN_SECRET_NAME, ARGOCD_TOKEN_SECRET_NAMESPACE)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise
    data = s.data or {}
    token_b64 = data.get("token")
    if not token_b64:
        return None
    try:
        return base64.b64decode(token_b64).decode().strip() or None
    except Exception:
        return None


async def _validate_argocd_token(token: str) -> bool:
    """Ping ArgoCD with the token. Return True iff it accepts (200/2xx).

    Used to decide whether the existing-token short-circuit is safe. If
    ArgoCD has invalidated the token (e.g. its account password rotated
    by a previous race), we should not trust the stale Secret and instead
    rotate fresh credentials.
    """
    base_url = settings.argocd_url.rstrip("/")
    if not base_url:
        return False
    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:  # noqa: S501
            r = await client.get(
                f"{base_url}/api/v1/applications",
                headers={"Authorization": f"Bearer {token}"},
                params={"limit": "1"},
            )
        return r.is_success
    except Exception as exc:
        logger.warning("Platform bootstrap: token validation request failed — %s", exc)
        # Conservative: treat network errors as "valid" to avoid rotating on
        # a transient network blip. The next pod boot will retry.
        return True


def _patch_argocd_cm_account() -> None:
    """Ensure argocd-cm has `accounts.iyziops-api: apiKey,login` data key."""
    cm = k8s_client.core_v1.read_namespaced_config_map(ARGOCD_CM_NAME, ARGOCD_NAMESPACE)
    data = dict(cm.data or {})
    desired = "apiKey,login"
    key = f"accounts.{ARGOCD_LOCAL_ACCOUNT}"
    if data.get(key) == desired:
        return
    data[key] = desired
    cm.data = data
    k8s_client.core_v1.replace_namespaced_config_map(ARGOCD_CM_NAME, ARGOCD_NAMESPACE, cm)
    logger.info("Platform bootstrap: patched argocd-cm with %s=%s", key, desired)


def _patch_argocd_secret_password(plain_password: str) -> None:
    """Set bcrypt hash of the iyziops-api account password into argocd-secret."""
    s = k8s_client.core_v1.read_namespaced_secret(ARGOCD_SECRET_NAME, ARGOCD_NAMESPACE)
    data = dict(s.data or {})
    bcrypt_hash = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()
    mtime = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    data[f"accounts.{ARGOCD_LOCAL_ACCOUNT}.password"] = base64.b64encode(bcrypt_hash.encode()).decode()
    data[f"accounts.{ARGOCD_LOCAL_ACCOUNT}.passwordMtime"] = base64.b64encode(mtime.encode()).decode()
    s.data = data
    k8s_client.core_v1.replace_namespaced_secret(ARGOCD_SECRET_NAME, ARGOCD_NAMESPACE, s)
    logger.info("Platform bootstrap: set %s account password in argocd-secret", ARGOCD_LOCAL_ACCOUNT)


def _patch_argocd_rbac_policy() -> None:
    """Append the iyziops-api role + binding to argocd-rbac-cm policy.csv if missing."""
    cm = k8s_client.core_v1.read_namespaced_config_map(ARGOCD_RBAC_CM_NAME, ARGOCD_NAMESPACE)
    data = dict(cm.data or {})
    csv = data.get("policy.csv", "")
    if f"role:{ARGOCD_LOCAL_ACCOUNT}" in csv:
        return
    appended = (csv.rstrip("\n") + "\n" + "\n".join(ARGOCD_RBAC_LINES) + "\n").lstrip("\n")
    data["policy.csv"] = appended
    cm.data = data
    k8s_client.core_v1.replace_namespaced_config_map(ARGOCD_RBAC_CM_NAME, ARGOCD_NAMESPACE, cm)
    logger.info("Platform bootstrap: appended role:%s to argocd-rbac-cm policy.csv", ARGOCD_LOCAL_ACCOUNT)


async def _argocd_login_and_mint_token(plain_password: str) -> str:
    """Login as iyziops-api with plain_password, then mint a persistent API token."""
    base_url = settings.argocd_url.rstrip("/")
    async with httpx.AsyncClient(verify=False, timeout=15.0) as client:  # noqa: S501
        # 1. Login → JWT
        login = await client.post(
            f"{base_url}/api/v1/session",
            json={"username": ARGOCD_LOCAL_ACCOUNT, "password": plain_password},
        )
        login.raise_for_status()
        jwt = login.json()["token"]

        # 2. Mint persistent token (no expiration). Cap with a stable id so
        # repeated calls don't accumulate token entries.
        mint = await client.post(
            f"{base_url}/api/v1/account/{ARGOCD_LOCAL_ACCOUNT}/token",
            headers={"Authorization": f"Bearer {jwt}"},
            json={"id": "iyziops-api-bootstrap"},
        )
        mint.raise_for_status()
        return mint.json()["token"]


def _write_token_secret(token: str) -> bool:
    """Create-or-replace the iyziops-argocd-token Secret in haven-system.

    Returns True if a new Secret was created (= the running pod doesn't yet
    have ARGOCD_AUTH_TOKEN injected and needs a restart to pick it up).
    """
    encoded = base64.b64encode(token.encode()).decode()
    secret = V1Secret(
        api_version="v1",
        kind="Secret",
        metadata=V1ObjectMeta(
            name=ARGOCD_TOKEN_SECRET_NAME,
            namespace=ARGOCD_TOKEN_SECRET_NAMESPACE,
            labels={"haven.io/managed": "true", "haven.io/component": "argocd-auth"},
        ),
        data={"token": encoded},
        type="Opaque",
    )
    try:
        k8s_client.core_v1.create_namespaced_secret(ARGOCD_TOKEN_SECRET_NAMESPACE, secret)
        logger.info("Platform bootstrap: created Secret %s/%s", ARGOCD_TOKEN_SECRET_NAMESPACE, ARGOCD_TOKEN_SECRET_NAME)
        return True
    except ApiException as exc:
        if exc.status != 409:
            raise
    k8s_client.core_v1.replace_namespaced_secret(ARGOCD_TOKEN_SECRET_NAME, ARGOCD_TOKEN_SECRET_NAMESPACE, secret)
    logger.info("Platform bootstrap: replaced Secret %s/%s", ARGOCD_TOKEN_SECRET_NAMESPACE, ARGOCD_TOKEN_SECRET_NAME)
    return False


def _trigger_iyziops_api_rollout() -> None:
    """Trigger a rolling restart of iyziops-api Deployment.

    kubelet does NOT propagate Secret changes into env-var bindings — once a
    pod is running with `valueFrom.secretKeyRef` for an ARGOCD_AUTH_TOKEN
    Secret that didn't exist at start, the env var is unset and the pod
    needs a restart to pick up the now-populated value. This is the same
    annotation `kubectl rollout restart` uses.
    """
    if k8s_client.apps_v1 is None:
        logger.warning("Platform bootstrap: apps_v1 client unavailable — skipping self-rollout")
        return
    body = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "haven.io/restart-reason": "argocd-token-bootstrap",
                    }
                }
            }
        }
    }
    try:
        k8s_client.apps_v1.patch_namespaced_deployment(
            name="iyziops-api", namespace=ARGOCD_TOKEN_SECRET_NAMESPACE, body=body
        )
        logger.info(
            "Platform bootstrap: triggered self-rollout of iyziops-api so the new "
            "ARGOCD_AUTH_TOKEN env var lands in a fresh pod"
        )
    except ApiException as exc:
        logger.warning("Platform bootstrap: self-rollout patch failed — %s", exc)


async def ensure_argocd_api_token() -> None:
    """Ensure iyziops-api has a working ArgoCD API token.

    Idempotent and non-fatal — any single step failing is logged and skipped
    so the API can still serve requests that don't depend on ArgoCD polling.
    """
    if not k8s_client.is_available() or k8s_client.core_v1 is None:
        logger.warning("Platform bootstrap: K8s client unavailable — skipping ArgoCD token")
        return
    if not settings.argocd_url:
        logger.warning("Platform bootstrap: argocd_url empty — skipping ArgoCD token")
        return

    try:
        existing = _read_existing_argocd_token()
    except Exception:
        logger.exception("Platform bootstrap: read existing ArgoCD token failed")
        return

    # Validate-then-rotate: the Secret is the system-of-record for the token,
    # but ArgoCD is the system-of-record for whether the token is *still* valid
    # (it can invalidate tokens whenever account.passwordMtime advances). If the
    # stored token still works → no-op. If ArgoCD rejects it (401 due to a prior
    # password rotation race, or 404 if the account was wiped), fall through to
    # re-rotate + re-mint + overwrite the Secret.
    if existing and await _validate_argocd_token(existing):
        logger.info("Platform bootstrap: ArgoCD token still valid — skipping mint")
        return
    if existing:
        logger.warning(
            "Platform bootstrap: stored ArgoCD token rejected by ArgoCD (likely a "
            "prior password rotation invalidated it) — re-minting fresh credentials"
        )

    plain = secrets.token_urlsafe(32)
    try:
        _patch_argocd_cm_account()
        _patch_argocd_secret_password(plain)
        _patch_argocd_rbac_policy()
    except Exception:
        logger.exception("Platform bootstrap: failed to provision ArgoCD account/RBAC")
        return

    # Give argocd-server's in-process informer ~3s to pick up the changes.
    await asyncio.sleep(3)

    try:
        token = await _argocd_login_and_mint_token(plain)
    except Exception:
        logger.exception("Platform bootstrap: ArgoCD login + mint failed")
        return

    try:
        created_new_secret = _write_token_secret(token)
    except Exception:
        logger.exception("Platform bootstrap: write ArgoCD token Secret failed")
        return

    logger.info("Platform bootstrap: ArgoCD API token ready (account=%s)", ARGOCD_LOCAL_ACCOUNT)

    # First-boot scenario: the running pod started without ARGOCD_AUTH_TOKEN
    # because the Secret didn't exist yet. kubelet doesn't propagate Secret
    # changes into env-var bindings, so we self-trigger a rolling restart so
    # the next pod picks up the value. Subsequent boots see the existing
    # Secret + short-circuit at the top, so this rollout only happens once
    # per cluster install.
    if created_new_secret:
        try:
            _trigger_iyziops_api_rollout()
        except Exception:
            logger.exception("Platform bootstrap: self-rollout patch raised")


async def run_platform_bootstrap() -> None:
    """Run all bootstrap steps. Non-fatal on any single failure."""
    await ensure_haven_gitops_repo()
    try:
        ensure_argocd_gitea_repo_secret()
    except Exception:
        logger.exception("Platform bootstrap: ArgoCD gitea-repo secret step raised")
    try:
        await ensure_argocd_api_token()
    except Exception:
        logger.exception("Platform bootstrap: ArgoCD API token step raised")
