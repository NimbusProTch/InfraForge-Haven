"""Harbor Admin API integration — per-tenant project and robot account management.

Each tenant gets:
  - A dedicated Harbor project: tenant-{slug}  (private, storage-quota by tier)
  - A robot account with push+pull access to that project
  - The robot credentials are stored as harbor-{slug}-pull-secret in the tenant namespace

The build pipeline continues to use admin credentials via harbor-registry-secret for now.
Per-tenant robot credentials become the pull secret for deployed workloads.
"""

import base64
import json
import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Storage quota per tier in bytes (Harbor API expects bytes)
_GiB = 1024**3
_TiB = 1024**4

_TIER_STORAGE_QUOTA: dict[str, int] = {
    "free": 5 * _GiB,
    "dev": 20 * _GiB,
    "starter": 20 * _GiB,
    "standard": 100 * _GiB,
    "pro": 100 * _GiB,
    "premium": 500 * _GiB,
    "enterprise": _TiB,
}

_DEFAULT_TIER = "free"


@dataclass
class RobotCredentials:
    robot_name: str  # full robot name as returned by Harbor (e.g. "robot$tenant-acme+haven")
    secret: str  # robot account secret / password


class HarborService:
    """Manages Harbor projects and robot accounts via Harbor v2 API."""

    def __init__(self) -> None:
        self._base_url = settings.harbor_url.rstrip("/") + "/api/v2.0"
        self._auth = ("admin", settings.harbor_admin_password)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_project(self, tenant_slug: str, tier: str = _DEFAULT_TIER) -> None:
        """Create a private Harbor project for the tenant.

        Project name: tenant-{slug}
        Storage quota is determined by tier.
        Idempotent: 409 (already exists) is silently ignored.
        """
        project_name = f"tenant-{tenant_slug}"
        storage_limit = _TIER_STORAGE_QUOTA.get(tier, _TIER_STORAGE_QUOTA[_DEFAULT_TIER])

        payload = {
            "project_name": project_name,
            "public": False,
            "storage_limit": storage_limit,
            "metadata": {
                "auto_scan": "true",
                "prevent_vul": "false",
            },
        }

        async with self._client() as client:
            resp = await client.post("/projects", json=payload)
            if resp.status_code == 409:
                logger.info("Harbor project %s already exists — skipping creation", project_name)
                return
            resp.raise_for_status()
            logger.info("Created Harbor project %s (tier=%s, quota=%d GiB)", project_name, tier, storage_limit // _GiB)

    async def delete_project(self, tenant_slug: str) -> None:
        """Delete the tenant's Harbor project and all its repositories.

        Attempts to delete all repositories first (Harbor requires empty project to delete).
        404 is ignored (project may not exist).
        """
        project_name = f"tenant-{tenant_slug}"

        async with self._client() as client:
            # Delete all repositories in the project first
            repos_resp = await client.get(f"/projects/{project_name}/repositories", params={"page_size": 100})
            if repos_resp.status_code == 404:
                logger.info("Harbor project %s not found — nothing to delete", project_name)
                return
            if repos_resp.is_success:
                for repo in repos_resp.json():
                    repo_name = repo["name"].split("/", 1)[-1]
                    del_resp = await client.delete(f"/projects/{project_name}/repositories/{repo_name}")
                    if del_resp.is_success or del_resp.status_code == 404:
                        logger.debug("Deleted repository %s from project %s", repo_name, project_name)
                    else:
                        logger.warning("Failed to delete repository %s: %s", repo_name, del_resp.text)

            # Clear session cookies before DELETE — Harbor sets a session cookie on GET
            # which triggers CSRF token validation on subsequent mutating requests
            client.cookies.clear()

            # Delete the project
            resp = await client.delete(f"/projects/{project_name}")
            if resp.status_code == 404:
                return
            resp.raise_for_status()
            logger.info("Deleted Harbor project %s", project_name)

    async def create_robot_account(self, tenant_slug: str) -> RobotCredentials:
        """Create a robot account with push+pull access to tenant-{slug} project.

        Robot name: haven-{slug}
        Full robot name returned by Harbor: robot$tenant-{slug}+haven-{slug}
        Idempotent: existing robot with same name is deleted and recreated.
        """
        project_name = f"tenant-{tenant_slug}"
        robot_short_name = f"haven-{tenant_slug}"

        payload = {
            "name": robot_short_name,
            "description": f"Haven platform robot for tenant {tenant_slug}",
            "duration": -1,  # never expires
            "level": "project",
            "permissions": [
                {
                    "kind": "project",
                    "namespace": project_name,
                    "access": [
                        {"resource": "repository", "action": "push"},
                        {"resource": "repository", "action": "pull"},
                        {"resource": "artifact", "action": "read"},
                        {"resource": "tag", "action": "create"},
                    ],
                }
            ],
        }

        async with self._client() as client:
            # Delete existing robot with same name if any (idempotent re-create)
            await self._delete_existing_robot(client, project_name, robot_short_name)

            # Clear session cookies — Harbor CSRF requires token after session cookie set
            client.cookies.clear()
            resp = await client.post("/robots", json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Created Harbor robot account %s for project %s", data.get("name"), project_name)
            return RobotCredentials(
                robot_name=data["name"],
                secret=data["secret"],
            )

    def build_imagepull_secret(self, tenant_slug: str, creds: RobotCredentials) -> dict:
        """Build a Kubernetes imagePullSecret manifest from robot credentials.

        The secret is named harbor-{slug}-pull-secret and should be created
        in the tenant namespace by the caller (TenantService).
        """
        from urllib.parse import urlparse

        harbor_host = urlparse(settings.harbor_url).netloc or settings.harbor_url.rstrip("/")
        auth_str = base64.b64encode(f"{creds.robot_name}:{creds.secret}".encode()).decode()
        docker_config = {"auths": {harbor_host: {"auth": auth_str}}}
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": f"harbor-{tenant_slug}-pull-secret",
            },
            "type": "kubernetes.io/dockerconfigjson",
            "data": {".dockerconfigjson": base64.b64encode(json.dumps(docker_config).encode()).decode()},
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            auth=self._auth,
            timeout=30,
            verify=False,  # Harbor behind self-signed cert in dev  # noqa: S501
        )

    async def _delete_existing_robot(self, client: httpx.AsyncClient, project_name: str, robot_short_name: str) -> None:
        """List project robots and delete one matching robot_short_name if found."""
        resp = await client.get(f"/projects/{project_name}/robots", params={"page_size": 100})
        if not resp.is_success:
            return
        for robot in resp.json():
            # Harbor stores robot name as "robot$project+shortname"
            if robot.get("name", "").endswith(f"+{robot_short_name}"):
                del_resp = await client.delete(f"/projects/{project_name}/robots/{robot['id']}")
                if del_resp.is_success:
                    logger.debug("Deleted existing robot %s before recreate", robot["name"])
                break


harbor_service = HarborService()
