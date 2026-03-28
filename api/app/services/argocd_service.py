"""ArgoCD API client for monitoring deployment status.

Polls ArgoCD Application health after GitOps commits to track
whether resources have been successfully synced to the cluster.
"""

import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ArgoCDService:
    """Interacts with ArgoCD API to monitor and trigger application syncs."""

    def __init__(
        self,
        argocd_url: str = "",
        auth_token: str = "",
    ) -> None:
        self._url = (argocd_url or settings.argocd_url).rstrip("/")
        self._token = auth_token or settings.argocd_auth_token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def get_app_status(self, app_name: str) -> dict:
        """Get ArgoCD Application status.

        Returns dict with keys: health, sync, operationState, or empty dict on failure.
        """
        if not self._url:
            return {}

        try:
            async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
                response = await client.get(
                    f"{self._url}/api/v1/applications/{app_name}",
                    headers=self._headers(),
                    timeout=15.0,
                )
            if response.status_code == 404:
                return {"health": "Missing", "sync": "Unknown"}
            if not response.is_success:
                logger.warning("ArgoCD API error: %d for app %s", response.status_code, app_name)
                return {}

            data = response.json()
            status = data.get("status", {})
            return {
                "health": status.get("health", {}).get("status", "Unknown"),
                "sync": status.get("sync", {}).get("status", "Unknown"),
                "operationState": status.get("operationState", {}),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArgoCD API unreachable: %s", exc)
            return {}

    async def wait_for_healthy(
        self, app_name: str, timeout: int = 180
    ) -> tuple[bool, str]:
        """Poll ArgoCD Application until Healthy+Synced or timeout.

        Returns (success, message).
        """
        if not self._url:
            logger.info("ArgoCD URL not configured — skipping health check for %s", app_name)
            return True, "ArgoCD not configured (skipped)"

        for i in range(timeout // 5):
            status = await self.get_app_status(app_name)
            health = status.get("health", "Unknown")
            sync = status.get("sync", "Unknown")

            logger.debug("ArgoCD app %s: health=%s sync=%s (poll %d)", app_name, health, sync, i)

            if health == "Healthy" and sync == "Synced":
                return True, f"Application {app_name} is Healthy and Synced"

            if health == "Degraded":
                op_state = status.get("operationState", {})
                msg = op_state.get("message", "Degraded")
                return False, f"Application {app_name} degraded: {msg}"

            await asyncio.sleep(5)

        return False, f"Application {app_name} not healthy after {timeout}s"

    async def trigger_sync(self, app_name: str) -> bool:
        """Trigger an ArgoCD sync for immediate reconciliation."""
        if not self._url:
            return False

        try:
            async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
                response = await client.post(
                    f"{self._url}/api/v1/applications/{app_name}/sync",
                    headers=self._headers(),
                    json={"prune": True},
                    timeout=15.0,
                )
            if response.is_success:
                logger.info("Triggered sync for ArgoCD app %s", app_name)
                return True
            logger.warning("ArgoCD sync trigger failed: %d", response.status_code)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArgoCD sync trigger error: %s", exc)
            return False

    async def get_app_resources(self, app_name: str) -> list[dict]:
        """Get managed resources for an ArgoCD Application."""
        if not self._url:
            return []

        try:
            async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
                response = await client.get(
                    f"{self._url}/api/v1/applications/{app_name}/managed-resources",
                    headers=self._headers(),
                    timeout=15.0,
                )
            if response.is_success:
                return response.json().get("items", [])
            return []
        except Exception:  # noqa: BLE001
            return []

    async def get_app_history(self, app_name: str) -> list[dict]:
        """Get deployment history for an ArgoCD Application.

        Returns list of revision records from status.history, each containing:
          id (int), revision (git SHA), deployedAt, source, etc.
        Returns empty list on failure or when ArgoCD is not configured.
        """
        if not self._url:
            return []

        try:
            async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
                response = await client.get(
                    f"{self._url}/api/v1/applications/{app_name}",
                    headers=self._headers(),
                    timeout=15.0,
                )
            if not response.is_success:
                logger.warning("ArgoCD get history failed: %d for app %s", response.status_code, app_name)
                return []
            data = response.json()
            return data.get("status", {}).get("history", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArgoCD get history error for %s: %s", app_name, exc)
            return []

    async def rollback_app(self, app_name: str, revision: int) -> bool:
        """Rollback an ArgoCD Application to a specific history revision ID.

        Args:
            app_name: ArgoCD Application name (e.g. "gemeente-a-my-app")
            revision: Integer history ID from status.history[].id

        Returns:
            True if rollback was triggered successfully, False otherwise.
        """
        if not self._url:
            return False

        try:
            async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
                response = await client.post(
                    f"{self._url}/api/v1/applications/{app_name}/rollback",
                    headers=self._headers(),
                    json={"id": revision},
                    timeout=15.0,
                )
            if response.is_success:
                logger.info("Triggered rollback for ArgoCD app %s to revision %d", app_name, revision)
                return True
            logger.warning(
                "ArgoCD rollback failed: %d for app %s revision %d",
                response.status_code, app_name, revision,
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArgoCD rollback error for %s: %s", app_name, exc)
            return False
