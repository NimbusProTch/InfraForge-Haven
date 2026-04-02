"""HashiCorp Vault KV v2 API client for sensitive environment variables.

Secrets are stored at: haven/tenants/{tenant_slug}/apps/{app_slug}/secrets
ESO (External Secrets Operator) syncs Vault secrets to K8s Secrets automatically.

When Vault is not configured (VAULT_URL empty), falls back to direct K8s Secrets.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

VAULT_URL = settings.vault_url
VAULT_TOKEN = settings.vault_token


def _vault_path(tenant_slug: str, app_slug: str) -> str:
    """Vault KV v2 path for an app's sensitive env vars."""
    return f"haven/data/tenants/{tenant_slug}/apps/{app_slug}/secrets"


def _vault_metadata_path(tenant_slug: str, app_slug: str) -> str:
    """Vault KV v2 metadata path for an app's sensitive env vars."""
    return f"haven/metadata/tenants/{tenant_slug}/apps/{app_slug}/secrets"


class VaultService:
    """Manages sensitive env vars in HashiCorp Vault KV v2."""

    def __init__(self, url: str = VAULT_URL, token: str = VAULT_TOKEN) -> None:
        self._url = url.rstrip("/") if url else ""
        self._token = token

    def is_configured(self) -> bool:
        """Return True if Vault URL and token are set."""
        return bool(self._url and self._token)

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make authenticated request to Vault API."""
        headers = {"X-Vault-Token": self._token}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(
                method,
                f"{self._url}/v1/{path}",
                headers=headers,
                **kwargs,
            )
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()

    async def write_secrets(self, tenant_slug: str, app_slug: str, data: dict[str, str]) -> None:
        """Write sensitive env vars to Vault. ESO will sync to K8s Secret."""
        path = _vault_path(tenant_slug, app_slug)
        await self._request("POST", path, json={"data": data})
        logger.info("Vault: wrote %d keys to %s", len(data), path)

    async def read_secrets(self, tenant_slug: str, app_slug: str) -> dict[str, str]:
        """Read sensitive env vars from Vault. Returns empty dict if not found."""
        path = _vault_path(tenant_slug, app_slug)
        try:
            result = await self._request("GET", path)
            return result.get("data", {}).get("data", {})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {}
            raise

    async def delete_secrets(self, tenant_slug: str, app_slug: str) -> None:
        """Delete sensitive env vars from Vault."""
        path = _vault_metadata_path(tenant_slug, app_slug)
        try:
            await self._request("DELETE", path)
            logger.info("Vault: deleted secrets at %s", path)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return
            raise

    async def list_keys(self, tenant_slug: str, app_slug: str) -> list[str]:
        """List secret keys (not values) for an app."""
        data = await self.read_secrets(tenant_slug, app_slug)
        return list(data.keys())


# Singleton
vault_service = VaultService()
