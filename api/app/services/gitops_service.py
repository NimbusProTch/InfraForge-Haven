"""GitOps service: manages tenant app and service manifests in a git repository.

Instead of directly calling K8s API, writes Helm values files to a git repo.
ArgoCD ApplicationSet detects changes and syncs resources to the cluster.
"""

import asyncio
import logging
import os
from pathlib import Path

import yaml

from app.config import settings

logger = logging.getLogger(__name__)


class GitOpsService:
    """Manages tenant deployment manifests in the haven-gitops repository."""

    def __init__(
        self,
        repo_url: str = "",
        branch: str = "main",
        clone_dir: str = "/tmp/haven-gitops",
        deploy_key_path: str = "",
    ) -> None:
        self._repo_url = repo_url or settings.gitops_repo_url
        self._branch = branch
        self._clone_dir = Path(clone_dir)
        self._deploy_key_path = deploy_key_path or settings.gitops_deploy_key_path
        self._lock = asyncio.Lock()
        self._initialized = False

    def _git_env(self) -> dict[str, str]:
        """Build environment for git commands with optional deploy key."""
        env = os.environ.copy()
        if self._deploy_key_path and Path(self._deploy_key_path).exists():
            env["GIT_SSH_COMMAND"] = (
                f"ssh -i {self._deploy_key_path} -o StrictHostKeyChecking=no"
            )
        return env

    async def _run_git(self, *args: str, cwd: Path | None = None) -> str:
        """Run a git command asynchronously."""
        cmd = ["git"] + list(args)
        work_dir = str(cwd or self._clone_dir)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._git_env(),
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            logger.error("git %s failed: %s", " ".join(args), err_msg)
            raise RuntimeError(f"git {args[0]} failed: {err_msg}")

        return stdout.decode().strip()

    async def _ensure_repo(self) -> None:
        """Clone if not exists, pull if exists."""
        if not self._repo_url:
            logger.warning("GitOps repo URL not configured — operating in local-only mode")
            self._clone_dir.mkdir(parents=True, exist_ok=True)
            if not (self._clone_dir / ".git").exists():
                await self._run_git("init", cwd=self._clone_dir)
                await self._run_git("checkout", "-b", self._branch, cwd=self._clone_dir)
            self._initialized = True
            return

        if self._initialized and (self._clone_dir / ".git").exists():
            try:
                await self._run_git("pull", "--rebase", "origin", self._branch)
                return
            except RuntimeError:
                logger.warning("git pull failed, re-cloning")

        if (self._clone_dir / ".git").exists():
            # Already cloned, just pull
            try:
                await self._run_git("pull", "--rebase", "origin", self._branch)
                self._initialized = True
                return
            except RuntimeError:
                pass

        # Fresh clone
        self._clone_dir.mkdir(parents=True, exist_ok=True)
        await self._run_git(
            "clone", "--depth=1", "--branch", self._branch,
            self._repo_url, str(self._clone_dir),
            cwd=Path("/tmp"),
        )
        self._initialized = True

    async def _commit_and_push(self, message: str) -> str:
        """Stage all changes, commit, and push. Returns commit SHA."""
        await self._run_git("add", "-A")

        # Check if there are changes to commit
        try:
            await self._run_git("diff", "--cached", "--quiet")
            logger.info("No changes to commit")
            result = await self._run_git("rev-parse", "HEAD")
            return result
        except RuntimeError:
            pass  # There are staged changes

        await self._run_git(
            "commit", "-m", message,
            "--author", "Haven Platform <haven@haven.dev>",
        )
        sha = await self._run_git("rev-parse", "HEAD")

        if self._repo_url:
            try:
                await self._run_git("push", "origin", self._branch)
                logger.info("Pushed to %s: %s", self._branch, sha[:8])
            except RuntimeError as e:
                logger.error("Push failed: %s", e)
                # Pull-rebase-push retry
                await self._run_git("pull", "--rebase", "origin", self._branch)
                await self._run_git("push", "origin", self._branch)
                sha = await self._run_git("rev-parse", "HEAD")

        return sha

    async def write_app_values(
        self, tenant_slug: str, app_slug: str, values: dict
    ) -> str:
        """Write values.yaml for a tenant app, commit, and push. Returns commit SHA."""
        async with self._lock:
            await self._ensure_repo()

            app_dir = self._clone_dir / "tenants" / tenant_slug / app_slug
            app_dir.mkdir(parents=True, exist_ok=True)

            values_path = app_dir / "values.yaml"
            values_path.write_text(yaml.dump(values, default_flow_style=False, sort_keys=False))

            return await self._commit_and_push(
                f"[haven] deploy {tenant_slug}/{app_slug} image={values.get('image', {}).get('tag', 'unknown')}"
            )

    async def write_service_values(
        self, tenant_slug: str, service_name: str, values: dict
    ) -> str:
        """Write values.yaml for a managed service, commit, and push."""
        async with self._lock:
            await self._ensure_repo()

            svc_dir = self._clone_dir / "tenants" / tenant_slug / "services" / service_name
            svc_dir.mkdir(parents=True, exist_ok=True)

            values_path = svc_dir / "values.yaml"
            values_path.write_text(yaml.dump(values, default_flow_style=False, sort_keys=False))

            return await self._commit_and_push(
                f"[haven] provision {tenant_slug}/services/{service_name} type={values.get('serviceType', 'unknown')}"
            )

    async def delete_app(self, tenant_slug: str, app_slug: str) -> str:
        """Remove app directory, commit, push. ArgoCD prunes the K8s resources."""
        async with self._lock:
            await self._ensure_repo()

            app_dir = self._clone_dir / "tenants" / tenant_slug / app_slug
            if app_dir.exists():
                import shutil
                shutil.rmtree(app_dir)

            return await self._commit_and_push(
                f"[haven] delete {tenant_slug}/{app_slug}"
            )

    async def delete_service(self, tenant_slug: str, service_name: str) -> str:
        """Remove service directory, commit, push."""
        async with self._lock:
            await self._ensure_repo()

            svc_dir = self._clone_dir / "tenants" / tenant_slug / "services" / service_name
            if svc_dir.exists():
                import shutil
                shutil.rmtree(svc_dir)

            return await self._commit_and_push(
                f"[haven] deprovision {tenant_slug}/services/{service_name}"
            )

    async def delete_tenant(self, tenant_slug: str) -> str:
        """Remove entire tenant directory, commit, push."""
        async with self._lock:
            await self._ensure_repo()

            tenant_dir = self._clone_dir / "tenants" / tenant_slug
            if tenant_dir.exists():
                import shutil
                shutil.rmtree(tenant_dir)

            return await self._commit_and_push(
                f"[haven] delete tenant {tenant_slug}"
            )
