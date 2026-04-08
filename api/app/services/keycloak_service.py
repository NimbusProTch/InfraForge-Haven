"""Keycloak Admin REST API service for tenant member provisioning.

H3a (P2.1) — 2026-04-09: This file used to host the per-tenant realm
automation lifecycle (`create_realm`, `delete_realm`, `create_client`,
`enable_self_registration`, `is_available`). All of those methods were
explicitly disabled in `routers/tenants.py` since Sprint 1 (the platform
runs on a single shared "haven" realm) and had ZERO production callers
— they were only kept alive by `noqa: F401` imports and a handful of
"this method exists" assertion tests.

The audit + Sprint H3 cleanup removed them. The only Keycloak Admin
operation Haven actually performs today is `create_user` for the tenant
member invite flow (`routers/members.py`). That, and its `_get_admin_token`
+ `_assign_realm_role` dependencies, are what remains.

If per-tenant realms ever come back (Sprint 5+ for IdP federation), the
deleted methods can be reconstructed from git history at commit be21561's
parent — they were not load-bearing complexity, just dead code.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class KeycloakService:
    """Tenant member provisioning via Keycloak Admin REST API.

    All operations target the shared "haven" realm (settings.keycloak_realm).
    """

    def __init__(self) -> None:
        self._base_url = settings.keycloak_url.rstrip("/")
        self._admin_user = settings.keycloak_admin_user
        self._admin_password = settings.keycloak_admin_password
        self._client_id = settings.keycloak_admin_client_id

    # ------------------------------------------------------------------
    # Admin token
    # ------------------------------------------------------------------

    async def _get_admin_token(self) -> str:
        """Obtain a short-lived admin access token from the master realm."""
        url = f"{self._base_url}/realms/master/protocol/openid-connect/token"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                data={
                    "grant_type": "password",
                    "client_id": self._client_id,
                    "username": self._admin_user,
                    "password": self._admin_password,
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def create_user(
        self,
        tenant_slug: str,
        username: str,
        email: str,
        password: str,
        *,
        role: str = "tenant_admin",
    ) -> str:
        """Create a user in the tenant realm and return their Keycloak user ID."""
        realm_name = f"tenant-{tenant_slug}"
        token = await self._get_admin_token()

        async with httpx.AsyncClient(timeout=15) as client:
            # Create user
            create_resp = await client.post(
                f"{self._base_url}/admin/realms/{realm_name}/users",
                json={
                    "username": username,
                    "email": email,
                    "enabled": True,
                    "emailVerified": True,
                    "credentials": [{"type": "password", "value": password, "temporary": False}],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            if create_resp.status_code == 409:
                logger.info("User %s in realm %s already exists", username, realm_name)
                # Retrieve existing user ID
                search_resp = await client.get(
                    f"{self._base_url}/admin/realms/{realm_name}/users",
                    params={"username": username, "exact": "true"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                search_resp.raise_for_status()
                users = search_resp.json()
                return users[0]["id"] if users else ""

            create_resp.raise_for_status()
            # Location header contains /admin/realms/{realm}/users/{id}
            location = create_resp.headers.get("Location", "")
            user_id = location.rsplit("/", 1)[-1]

        await self._assign_realm_role(tenant_slug, user_id, role)
        logger.info("Created user %s in realm %s (id=%s)", username, realm_name, user_id)
        return user_id

    async def _assign_realm_role(self, tenant_slug: str, user_id: str, role_name: str) -> None:
        """Create and assign a realm-level role to a user.

        Creates the role if it does not exist.
        """
        if not user_id:
            return
        realm_name = f"tenant-{tenant_slug}"
        token = await self._get_admin_token()

        async with httpx.AsyncClient(timeout=15) as client:
            # Ensure role exists
            create_role_resp = await client.post(
                f"{self._base_url}/admin/realms/{realm_name}/roles",
                json={"name": role_name, "description": f"Haven role: {role_name}"},
                headers={"Authorization": f"Bearer {token}"},
            )
            if create_role_resp.status_code not in (201, 409):
                create_role_resp.raise_for_status()

            # Fetch role representation
            role_resp = await client.get(
                f"{self._base_url}/admin/realms/{realm_name}/roles/{role_name}",
                headers={"Authorization": f"Bearer {token}"},
            )
            role_resp.raise_for_status()
            role_repr = role_resp.json()

            # Assign role to user
            assign_resp = await client.post(
                f"{self._base_url}/admin/realms/{realm_name}/users/{user_id}/role-mappings/realm",
                json=[role_repr],
                headers={"Authorization": f"Bearer {token}"},
            )
            assign_resp.raise_for_status()

        logger.info("Assigned role %s to user %s in realm %s", role_name, user_id, realm_name)


# Singleton instance — same pattern as k8s_client
keycloak_service = KeycloakService()
