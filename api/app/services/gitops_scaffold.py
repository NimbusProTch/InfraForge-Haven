"""GitOps scaffold service.

Creates and manages tenant/app values files in the haven-gitops Gitea repo.
ArgoCD ApplicationSet watches tenant directories and deploys resources automatically.

Repo layout:
  tenants/{tenant_slug}/{app_slug}/values.yaml  — haven-app Helm values
"""

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from app.config import settings
from app.services.gitea_client import GiteaClient, gitea_client

logger = logging.getLogger(__name__)

# Path to Jinja2 templates directory
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "gitops"


def _jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)


def _render(template_name: str, **ctx: Any) -> str:
    env = _jinja_env()
    tpl = env.get_template(template_name)
    return tpl.render(**ctx)


class GitOpsScaffold:
    """Manages tenant/app GitOps directory structure in the haven-gitops repo."""

    def __init__(
        self,
        client: GiteaClient | None = None,
        org: str = "",
        repo: str = "",
        branch: str = "",
    ) -> None:
        self._client = client or gitea_client
        self._org = org or settings.gitea_org
        self._repo = repo or settings.gitea_gitops_repo
        self._branch = branch or settings.gitea_gitops_branch

    def _is_configured(self) -> bool:
        return self._client._is_configured()

    # ------------------------------------------------------------------
    # Tenant lifecycle
    # ------------------------------------------------------------------

    async def scaffold_tenant(self, tenant_slug: str) -> None:
        """No-op: tenant directory is created lazily when the first app is scaffolded.

        Namespace is provisioned via K8s API (TenantService.provision), not GitOps.
        """
        logger.info("scaffold_tenant(%s) — no-op, directory created on first app scaffold", tenant_slug)

    async def delete_tenant(self, tenant_slug: str) -> None:
        """Remove all tenant files from haven-gitops."""
        if not self._is_configured():
            logger.info("GitOps not configured — skipping delete_tenant(%s)", tenant_slug)
            return
        try:
            await self._client.delete_directory(
                self._org,
                self._repo,
                f"tenants/{tenant_slug}",
                f"Haven API: delete tenant {tenant_slug}",
                self._branch,
            )
            logger.info("Deleted tenant '%s' from haven-gitops", tenant_slug)
        except Exception as exc:
            logger.error("delete_tenant(%s) failed: %s", tenant_slug, exc)

    # ------------------------------------------------------------------
    # App lifecycle
    # ------------------------------------------------------------------

    async def scaffold_app(
        self,
        tenant_slug: str,
        app_slug: str,
        *,
        port: int = 8000,
        replicas: int = 1,
        env_vars: dict[str, str] | None = None,
        image_repository: str = "",
        image_tag: str = "latest",
        cpu_request: str = "50m",
        memory_request: str = "64Mi",
        cpu_limit: str = "500m",
        memory_limit: str = "512Mi",
    ) -> None:
        """Create app values.yaml in haven-gitops."""
        if not self._is_configured():
            logger.info("GitOps not configured — skipping scaffold_app(%s/%s)", tenant_slug, app_slug)
            return
        try:
            content = _render(
                "app-values.yaml.j2",
                tenant_slug=tenant_slug,
                app_slug=app_slug,
                port=port,
                replicas=replicas,
                env_vars=env_vars or {},
                image_repository=image_repository,
                image_tag=image_tag,
                cpu_request=cpu_request,
                memory_request=memory_request,
                cpu_limit=cpu_limit,
                memory_limit=memory_limit,
            )
            await self._client.upsert_file(
                self._org,
                self._repo,
                f"tenants/{tenant_slug}/{app_slug}/values.yaml",
                content,
                f"Haven API: create app {app_slug} for tenant {tenant_slug}",
                self._branch,
            )
            logger.info("Scaffolded app '%s/%s' in haven-gitops", tenant_slug, app_slug)
        except Exception as exc:
            logger.error("scaffold_app(%s/%s) failed: %s", tenant_slug, app_slug, exc)

    async def delete_app(self, tenant_slug: str, app_slug: str) -> None:
        """Delete app values.yaml from haven-gitops."""
        if not self._is_configured():
            logger.info("GitOps not configured — skipping delete_app(%s/%s)", tenant_slug, app_slug)
            return
        try:
            await self._client.delete_directory(
                self._org,
                self._repo,
                f"tenants/{tenant_slug}/{app_slug}",
                f"Haven API: delete app {app_slug} for tenant {tenant_slug}",
                self._branch,
            )
            logger.info("Deleted app '%s/%s' from haven-gitops", tenant_slug, app_slug)
        except Exception as exc:
            logger.error("delete_app(%s/%s) failed: %s", tenant_slug, app_slug, exc)

    # ------------------------------------------------------------------


# Module-level singleton
gitops_scaffold = GitOpsScaffold()
