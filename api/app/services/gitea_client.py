"""Gitea HTTP API client.

Wraps Gitea's REST API v1 for repository and file CRUD operations.
Used by GitOpsScaffold to manage the haven-gitops repository.
"""

import base64
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_GITEA_TIMEOUT = 30.0


class GiteaClient:
    """Async Gitea API v1 client.

    All methods are safe to call when Gitea is not configured (gitea_url empty):
    they log a warning and return a neutral value.
    """

    def __init__(self, base_url: str = "", token: str = "") -> None:
        self._base_url = (base_url or settings.gitea_url).rstrip("/")
        self._token = token or settings.gitea_admin_token

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self._token}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self._base_url}/api/v1{path}"

    def _is_configured(self) -> bool:
        return bool(self._base_url and self._token)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int | tuple[int, ...] = 200,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an HTTP request and return the JSON response body."""
        async with httpx.AsyncClient(timeout=_GITEA_TIMEOUT) as client:
            resp = await client.request(
                method,
                self._url(path),
                headers=self._headers(),
                **kwargs,
            )
        if isinstance(expected_status, int):
            ok_codes: tuple[int, ...] = (expected_status,)
        else:
            ok_codes = expected_status
        if resp.status_code not in ok_codes:
            raise httpx.HTTPStatusError(
                f"Gitea {method} {path} → {resp.status_code}: {resp.text[:200]}",
                request=resp.request,
                response=resp,
            )
        if resp.content:
            return resp.json()  # type: ignore[no-any-return]
        return {}

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health(self) -> bool:
        """Return True if Gitea API is reachable."""
        if not self._is_configured():
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self._url("/version"), headers=self._headers())
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Organization
    # ------------------------------------------------------------------

    async def ensure_org(self, org: str) -> None:
        """Create organization if it does not already exist."""
        if not self._is_configured():
            logger.warning("Gitea not configured — skipping ensure_org(%s)", org)
            return
        try:
            await self._request("GET", f"/orgs/{org}", expected_status=200)
            logger.debug("Gitea org '%s' already exists", org)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                await self._request(
                    "POST",
                    "/orgs",
                    expected_status=201,
                    json={"username": org, "visibility": "private", "repo_admin_change_team_access": True},
                )
                logger.info("Created Gitea org '%s'", org)
            else:
                raise

    async def delete_org(self, org: str) -> None:
        """Delete organization. No-op if it does not exist."""
        if not self._is_configured():
            return
        try:
            await self._request("DELETE", f"/orgs/{org}", expected_status=(204, 404))
            logger.info("Deleted Gitea org '%s'", org)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.debug("Gitea org '%s' does not exist — nothing to delete", org)
            else:
                raise

    async def add_org_member(self, org: str, username: str, role: str = "member") -> None:
        """Add a user as a member of the organization's owners team."""
        if not self._is_configured():
            return
        # Gitea API: add user to the org owners team, or any team
        # First, get the org teams to find the appropriate team
        teams = await self._request("GET", f"/orgs/{org}/teams", expected_status=200)
        if not isinstance(teams, list):
            teams = [teams]
        target_team = None
        for team in teams:
            if role == "owner" and team.get("permission") == "owner":
                target_team = team
                break
            if role == "member" and team.get("name", "").lower() in ("owners", "developers", "members"):
                target_team = team
                break
        if target_team is None and teams:
            target_team = teams[0]  # fallback to first team
        if target_team:
            team_id = target_team["id"]
            await self._request("PUT", f"/teams/{team_id}/members/{username}", expected_status=(204, 200, 404))
            logger.info("Added user '%s' to org '%s' team '%s'", username, org, target_team.get("name"))

    async def list_org_repos(self, org: str, page: int = 1, limit: int = 50) -> list[dict[str, Any]]:
        """List repositories for an organization."""
        if not self._is_configured():
            return []
        try:
            result = await self._request(
                "GET",
                f"/orgs/{org}/repos",
                expected_status=200,
                params={"page": page, "limit": limit},
            )
            return result if isinstance(result, list) else [result]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            raise

    # ------------------------------------------------------------------
    # Repository
    # ------------------------------------------------------------------

    async def ensure_repo(self, owner: str, repo: str, *, default_branch: str = "main") -> None:
        """Create repository under owner (org or user) if it does not exist."""
        if not self._is_configured():
            logger.warning("Gitea not configured — skipping ensure_repo(%s/%s)", owner, repo)
            return
        try:
            await self._request("GET", f"/repos/{owner}/{repo}", expected_status=200)
            logger.debug("Gitea repo '%s/%s' already exists", owner, repo)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                await self._request(
                    "POST",
                    f"/orgs/{owner}/repos",
                    expected_status=201,
                    json={
                        "name": repo,
                        "private": True,
                        "auto_init": True,
                        "default_branch": default_branch,
                    },
                )
                logger.info("Created Gitea repo '%s/%s'", owner, repo)
            else:
                raise

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any] | None:
        """Get repository metadata. Returns None if not found."""
        if not self._is_configured():
            return None
        try:
            return await self._request("GET", f"/repos/{owner}/{repo}", expected_status=200)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def delete_repo(self, owner: str, repo: str) -> None:
        """Delete a repository. No-op if not found."""
        if not self._is_configured():
            return
        try:
            await self._request("DELETE", f"/repos/{owner}/{repo}", expected_status=(204, 404))
            logger.info("Deleted Gitea repo '%s/%s'", owner, repo)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.debug("Gitea repo '%s/%s' not found — nothing to delete", owner, repo)
            else:
                raise

    async def list_branches(self, owner: str, repo: str) -> list[dict[str, Any]]:
        """List branches for a repository."""
        if not self._is_configured():
            return []
        try:
            result = await self._request("GET", f"/repos/{owner}/{repo}/branches", expected_status=200)
            return result if isinstance(result, list) else [result]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            raise

    async def get_file_tree(
        self, owner: str, repo: str, ref: str = "main", *, recursive: bool = True
    ) -> list[dict[str, Any]]:
        """Get the git tree (file list) for a repository at a given ref."""
        if not self._is_configured():
            return []
        try:
            params: dict[str, Any] = {}
            if recursive:
                params["recursive"] = "true"
            result = await self._request(
                "GET",
                f"/repos/{owner}/{repo}/git/trees/{ref}",
                expected_status=200,
                params=params,
            )
            return result.get("tree", []) if isinstance(result, dict) else []
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            raise

    async def create_webhook(
        self,
        owner: str,
        repo: str,
        url: str,
        secret: str = "",
        events: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a push webhook on a repository."""
        if not self._is_configured():
            return {}
        payload: dict[str, Any] = {
            "type": "gitea",
            "active": True,
            "config": {
                "url": url,
                "content_type": "json",
            },
            "events": events or ["push"],
        }
        if secret:
            payload["config"]["secret"] = secret
        return await self._request(
            "POST",
            f"/repos/{owner}/{repo}/hooks",
            expected_status=201,
            json=payload,
        )

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    async def get_file(self, owner: str, repo: str, path: str, branch: str = "main") -> dict[str, Any] | None:
        """Return file metadata dict (including sha and content) or None if not found."""
        if not self._is_configured():
            return None
        try:
            return await self._request(
                "GET",
                f"/repos/{owner}/{repo}/contents/{path}",
                expected_status=200,
                params={"ref": branch},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def create_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
    ) -> str:
        """Create a file and return the commit SHA."""
        if not self._is_configured():
            logger.warning("Gitea not configured — skipping create_file %s/%s/%s", owner, repo, path)
            return ""
        encoded = base64.b64encode(content.encode()).decode()
        resp = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/contents/{path}",
            expected_status=201,
            json={"message": message, "content": encoded, "branch": branch},
        )
        return resp.get("commit", {}).get("sha", "")

    async def update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        sha: str,
        message: str,
        branch: str = "main",
    ) -> str:
        """Update an existing file and return the new commit SHA."""
        if not self._is_configured():
            logger.warning("Gitea not configured — skipping update_file %s/%s/%s", owner, repo, path)
            return ""
        encoded = base64.b64encode(content.encode()).decode()
        resp = await self._request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{path}",
            expected_status=200,
            json={"message": message, "content": encoded, "sha": sha, "branch": branch},
        )
        return resp.get("commit", {}).get("sha", "")

    async def delete_file(
        self,
        owner: str,
        repo: str,
        path: str,
        sha: str,
        message: str,
        branch: str = "main",
    ) -> str:
        """Delete a file and return the commit SHA."""
        if not self._is_configured():
            logger.warning("Gitea not configured — skipping delete_file %s/%s/%s", owner, repo, path)
            return ""
        resp = await self._request(
            "DELETE",
            f"/repos/{owner}/{repo}/contents/{path}",
            expected_status=200,
            json={"message": message, "sha": sha, "branch": branch},
        )
        return resp.get("commit", {}).get("sha", "")

    async def upsert_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
    ) -> str:
        """Create or update a file (auto-detects existing SHA). Returns commit SHA."""
        existing = await self.get_file(owner, repo, path, branch)
        if existing is None:
            return await self.create_file(owner, repo, path, content, message, branch)
        sha = existing.get("sha", "")
        # Decode existing content and compare to skip no-op commits
        existing_b64 = existing.get("content", "").replace("\n", "")
        if existing_b64 and base64.b64decode(existing_b64).decode() == content:
            logger.debug("Gitea upsert: no change for %s/%s/%s — skipping commit", owner, repo, path)
            existing_sha: str = existing.get("last_commit_sha", "")
            return existing_sha
        return await self.update_file(owner, repo, path, content, sha, message, branch)

    # ------------------------------------------------------------------
    # Directory operations
    # ------------------------------------------------------------------

    async def list_contents(
        self,
        owner: str,
        repo: str,
        path: str = "",
        branch: str = "main",
    ) -> list[dict[str, Any]]:
        """List directory contents. Returns empty list if path doesn't exist."""
        if not self._is_configured():
            return []
        try:
            result = await self._request(
                "GET",
                f"/repos/{owner}/{repo}/contents/{path}",
                expected_status=200,
                params={"ref": branch},
            )
            # Gitea returns a list for directories, dict for files
            if isinstance(result, list):
                return result
            return [result]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            raise

    async def delete_directory(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        branch: str = "main",
    ) -> None:
        """Recursively delete all files in a directory."""
        if not self._is_configured():
            logger.warning("Gitea not configured — skipping delete_directory %s/%s/%s", owner, repo, path)
            return
        entries = await self.list_contents(owner, repo, path, branch)
        for entry in entries:
            entry_type = entry.get("type")
            entry_path = entry.get("path", "")
            if entry_type == "dir":
                await self.delete_directory(owner, repo, entry_path, message, branch)
            elif entry_type == "file":
                sha = entry.get("sha", "")
                await self.delete_file(owner, repo, entry_path, sha, message, branch)


# Module-level singleton — lazily uses settings
gitea_client = GiteaClient()
