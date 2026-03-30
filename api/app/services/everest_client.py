"""Percona Everest REST API client for database provisioning.

Manages PostgreSQL, MySQL, and MongoDB via Everest's abstraction layer.
Redis and RabbitMQ are NOT managed by Everest — use direct K8s CRDs for those.
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Everest in-cluster URL
EVEREST_URL = getattr(settings, "everest_url", "") or "http://everest.everest-system.svc.cluster.local:8080"
EVEREST_USER = getattr(settings, "everest_admin_user", "") or "admin"
EVEREST_PASS = getattr(settings, "everest_admin_password", "") or "HavenEverest2026"
EVEREST_NS = getattr(settings, "everest_namespace", "") or "everest"

# Engine type mapping
ENGINE_MAP = {
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "mysql": "pxc",
    "pxc": "pxc",
    "mongodb": "psmdb",
    "mongo": "psmdb",
    "psmdb": "psmdb",
}

# Tier → resource configuration (defaults, overridden per-engine below)
# Everest enforces minimum CPU 600m for DB engines
TIER_CONFIG = {
    "dev": {"replicas": 1, "storage": "2Gi", "cpu": "1", "memory": "512Mi"},
    "prod": {"replicas": 3, "storage": "20Gi", "cpu": "2", "memory": "4Gi"},
}

# Engine-specific overrides (MySQL XtraDB 8.4 needs more memory + storage than PG/MongoDB)
_ENGINE_OVERRIDES: dict[str, dict[str, dict[str, str]]] = {
    "pxc": {
        "dev": {"memory": "2Gi", "storage": "5Gi"},     # MySQL 8.4 + Galera: 2Gi RAM, 5Gi disk minimum
        "prod": {"memory": "4Gi", "storage": "20Gi"},
    },
}


class EverestClient:
    """HTTP client for Percona Everest REST API."""

    def __init__(self, base_url: str = EVEREST_URL):
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{self._base_url}/v1/session",
                json={"username": EVEREST_USER, "password": EVEREST_PASS},
                timeout=10.0,
            )
            resp.raise_for_status()
            self._token = resp.json()["token"]
            return self._token

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                timeout=30.0,
                **kwargs,
            )
            if resp.status_code == 401:
                # Token expired, retry once
                self._token = None
                token = await self._get_token()
                headers = {"Authorization": f"Bearer {token}"}
                resp = await client.request(
                    method,
                    f"{self._base_url}{path}",
                    headers=headers,
                    timeout=30.0,
                    **kwargs,
                )
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()

    # ---- Database Engines ----

    async def list_engines(self) -> list[dict]:
        data = await self._request("GET", f"/v1/namespaces/{EVEREST_NS}/database-engines")
        return data.get("items", [])

    # ---- Database Clusters (CRUD) ----

    async def create_database(
        self,
        name: str,
        engine_type: str,
        tier: str = "dev",
        version: str | None = None,
    ) -> dict:
        """Create a database cluster via Everest API."""
        engine = ENGINE_MAP.get(engine_type.lower())
        if not engine:
            raise ValueError(f"Unsupported engine type: {engine_type}. Use: postgres, mysql, mongodb")

        cfg = TIER_CONFIG.get(tier, TIER_CONFIG["dev"])
        overrides = _ENGINE_OVERRIDES.get(engine, {}).get(tier, {})
        memory = overrides.get("memory", cfg["memory"])
        storage = overrides.get("storage", cfg["storage"])

        body: dict[str, Any] = {
            "apiVersion": "everest.percona.com/v1alpha1",
            "kind": "DatabaseCluster",
            "metadata": {"name": name},
            "spec": {
                "engine": {
                    "type": engine,
                    "replicas": cfg["replicas"],
                    "storage": {"size": storage},
                    "resources": {
                        "cpu": cfg["cpu"],
                        "memory": memory,
                    },
                },
                "proxy": {
                    "replicas": cfg["replicas"],
                },
            },
        }

        if version:
            body["spec"]["engine"]["version"] = version

        logger.info("Creating Everest DB: name=%s engine=%s tier=%s", name, engine, tier)
        return await self._request("POST", f"/v1/namespaces/{EVEREST_NS}/database-clusters", json=body)

    async def get_database_details(self, name: str) -> dict:
        """Return structured details for UI enrichment."""
        db = await self.get_database(name)
        spec = db.get("spec", {})
        status = db.get("status", {})
        engine = spec.get("engine", {})
        resources = engine.get("resources", {})
        return {
            "status": status.get("status", "unknown"),
            "engine_version": engine.get("version"),
            "replicas": engine.get("replicas"),
            "ready_replicas": status.get("ready"),
            "storage": engine.get("storage", {}).get("size"),
            "cpu": resources.get("cpu"),
            "memory": resources.get("memory"),
            "hostname": status.get("hostname"),
            "port": status.get("port"),
            "error_message": status.get("message"),
        }

    async def get_database(self, name: str) -> dict:
        return await self._request("GET", f"/v1/namespaces/{EVEREST_NS}/database-clusters/{name}")

    async def update_database(
        self,
        name: str,
        *,
        replicas: int | None = None,
        storage: str | None = None,
        cpu: str | None = None,
        memory: str | None = None,
    ) -> dict:
        """Update a database cluster via Everest API (GET → modify → PUT).

        Only provided fields are changed; others keep their current values.
        Everest requires resourceVersion for optimistic concurrency.
        """
        current = await self.get_database(name)
        spec = current["spec"]

        if replicas is not None:
            spec["engine"]["replicas"] = replicas
            spec.setdefault("proxy", {})["replicas"] = replicas
        if storage is not None:
            spec["engine"]["storage"]["size"] = storage
        if cpu is not None:
            spec["engine"]["resources"]["cpu"] = cpu
        if memory is not None:
            spec["engine"]["resources"]["memory"] = memory

        body = {
            "apiVersion": "everest.percona.com/v1alpha1",
            "kind": "DatabaseCluster",
            "metadata": {
                "name": name,
                "resourceVersion": current["metadata"]["resourceVersion"],
            },
            "spec": spec,
        }

        logger.info("Updating Everest DB: name=%s", name)
        return await self._request("PUT", f"/v1/namespaces/{EVEREST_NS}/database-clusters/{name}", json=body)

    async def delete_database(self, name: str) -> dict:
        logger.info("Deleting Everest DB: %s", name)
        return await self._request("DELETE", f"/v1/namespaces/{EVEREST_NS}/database-clusters/{name}")

    async def list_databases(self) -> list[dict]:
        data = await self._request("GET", f"/v1/namespaces/{EVEREST_NS}/database-clusters")
        return data.get("items", [])

    # ---- Status helpers ----

    async def get_database_status(self, name: str) -> str:
        """Return database status: 'initializing', 'ready', 'error', etc."""
        try:
            db = await self.get_database(name)
            return db.get("status", {}).get("status", "unknown")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return "not_found"
            raise

    async def get_credentials(self, name: str) -> dict[str, str]:
        """Get connection credentials from Everest.

        Note: Everest API status doesn't include credentials directly.
        Use K8s secret `everest-secrets-{name}` in the everest namespace instead.
        This method returns what's available from the API (hostname, port).
        """
        db = await self.get_database(name)
        status = db.get("status", {})
        return {
            "hostname": status.get("hostname", ""),
            "port": str(status.get("port", "")),
        }

    def is_configured(self) -> bool:
        return bool(self._base_url)


# Singleton
everest_client = EverestClient()
