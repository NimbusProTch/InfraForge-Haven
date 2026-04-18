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

    async def get_live_status(self, app_name: str) -> dict:
        """Compact, UI-friendly view of ArgoCD Application status.

        Returns:
            {
              "health":    "Healthy" | "Degraded" | "Progressing" | "Missing" | "Unknown",
              "sync":      "Synced"  | "OutOfSync" | "Unknown",
              "reason":    "<short human-readable explanation>" | "",
              "phase":     "<operation phase>" | "",
              "finished_at": "<ISO timestamp or empty>",
              "available": <bool — whether ArgoCD answered at all>,
            }

        The `reason` field is extracted from `status.operationState.message`,
        falling back to the latest of `status.conditions` so a Degraded app
        always carries enough context for the UI to render a one-line tooltip
        instead of just a red dot.
        """
        if not self._url:
            return {
                "health": "Unknown",
                "sync": "Unknown",
                "reason": "",
                "phase": "",
                "finished_at": "",
                "available": False,
            }

        try:
            async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
                response = await client.get(
                    f"{self._url}/api/v1/applications/{app_name}",
                    headers=self._headers(),
                    timeout=15.0,
                )
            if response.status_code == 404:
                return {
                    "health": "Missing",
                    "sync": "Unknown",
                    "reason": "Application not present in ArgoCD",
                    "phase": "",
                    "finished_at": "",
                    "available": True,
                }
            if not response.is_success:
                logger.warning("ArgoCD API error: %d for app %s", response.status_code, app_name)
                return {
                    "health": "Unknown",
                    "sync": "Unknown",
                    "reason": f"ArgoCD API error {response.status_code}",
                    "phase": "",
                    "finished_at": "",
                    "available": False,
                }

            data = response.json()
            status_block = data.get("status", {})
            health = status_block.get("health", {}).get("status", "Unknown")
            sync = status_block.get("sync", {}).get("status", "Unknown")
            op_state = status_block.get("operationState", {}) or {}

            reason = (op_state.get("message") or "").strip()
            if not reason and health in ("Degraded", "Missing"):
                # Fall back to the most recent non-empty condition message
                for cond in reversed(status_block.get("conditions", []) or []):
                    msg = (cond.get("message") or "").strip()
                    if msg:
                        reason = msg
                        break

            return {
                "health": health,
                "sync": sync,
                "reason": reason,
                "phase": op_state.get("phase", ""),
                "finished_at": op_state.get("finishedAt", ""),
                "available": True,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArgoCD API unreachable: %s", exc)
            return {
                "health": "Unknown",
                "sync": "Unknown",
                "reason": "",
                "phase": "",
                "finished_at": "",
                "available": False,
            }

    async def wait_for_healthy(self, app_name: str, timeout: int = 300) -> tuple[bool, str]:
        """Poll ArgoCD Application until Healthy or timeout.

        Accepts both Synced and OutOfSync — minor resource diffs (e.g. HTTPRoute)
        can cause OutOfSync while the app is fully operational.

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

            if health == "Healthy":
                return True, f"Application {app_name} is Healthy (sync={sync})"

            if health == "Degraded":
                op_state = status.get("operationState", {})
                msg = op_state.get("message", "Degraded")
                return False, f"Application {app_name} degraded: {msg}"

            await asyncio.sleep(5)

        return False, f"Application {app_name} not healthy after {timeout}s"

    async def trigger_sync(
        self,
        app_name: str,
        *,
        prune: bool = True,
        force: bool = False,
        dry_run: bool = False,
    ) -> bool:
        """Trigger an ArgoCD sync with configurable options.

        Args:
            prune: Remove resources that are no longer in git
            force: Override immutable field changes
            dry_run: Preview only, no actual changes
        """
        if not self._url:
            return False

        json_body: dict = {"prune": prune}
        if force:
            json_body["strategy"] = {"apply": {"force": True}}
        if dry_run:
            json_body["dryRun"] = True

        try:
            async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
                response = await client.post(
                    f"{self._url}/api/v1/applications/{app_name}/sync",
                    headers=self._headers(),
                    json=json_body,
                    timeout=15.0,
                )
            if response.is_success:
                logger.info(
                    "Triggered sync for ArgoCD app %s (prune=%s force=%s dry_run=%s)", app_name, prune, force, dry_run
                )
                return True
            logger.warning("ArgoCD sync trigger failed: %d", response.status_code)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArgoCD sync trigger error: %s", exc)
            return False

    async def get_resource_diff(self, app_name: str) -> list[dict]:
        """Get diff between live and target state for managed resources.

        Returns a list of resource diffs, each containing:
          kind, name, status (Synced/OutOfSync), diff (live vs target fields)
        """
        if not self._url:
            return []

        try:
            async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
                # Fetch app with refresh to get latest diff info
                response = await client.get(
                    f"{self._url}/api/v1/applications/{app_name}",
                    headers=self._headers(),
                    params={"refresh": "normal"},
                    timeout=20.0,
                )
            if not response.is_success:
                return []

            data = response.json()
            status = data.get("status", {})
            resources = status.get("resources", [])

            diffs = []
            for res in resources:
                sync_status = res.get("status", "Unknown")
                # Only include resources that are OutOfSync or have health issues
                if sync_status == "OutOfSync" or res.get("health", {}).get("status") not in ("Healthy", None):
                    diffs.append(
                        {
                            "kind": res.get("kind", ""),
                            "name": res.get("name", ""),
                            "namespace": res.get("namespace", ""),
                            "group": res.get("group", ""),
                            "version": res.get("version", ""),
                            "sync_status": sync_status,
                            "health_status": res.get("health", {}).get("status", ""),
                            "health_message": res.get("health", {}).get("message", ""),
                            "requires_pruning": res.get("requiresPruning", False),
                        }
                    )

            return diffs
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArgoCD get_resource_diff error for %s: %s", app_name, exc)
            return []

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
                response.status_code,
                app_name,
                revision,
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("ArgoCD rollback error for %s: %s", app_name, exc)
            return False
