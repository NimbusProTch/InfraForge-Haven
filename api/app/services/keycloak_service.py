"""Keycloak Admin REST API service for per-tenant realm automation."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class KeycloakService:
    """Automates Keycloak realm lifecycle via Admin REST API.

    One realm per tenant — full SSO isolation.
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
    # Master realm configuration
    # ------------------------------------------------------------------

    async def enable_self_registration(self, realm: str = "") -> None:
        """Enable self-service registration on a realm.

        If realm is empty, uses the platform master realm from settings.
        """
        target_realm = realm or settings.keycloak_realm
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.put(
                f"{self._base_url}/admin/realms/{target_realm}",
                json={"registrationAllowed": True},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
        logger.info("Enabled self-registration on realm: %s", target_realm)

    # ------------------------------------------------------------------
    # Realm lifecycle
    # ------------------------------------------------------------------

    async def create_realm(self, tenant_slug: str) -> None:
        """Create a dedicated Keycloak realm for a tenant.

        Realm name: tenant-{slug}
        Idempotent — does not raise if realm already exists.
        """
        realm_name = f"tenant-{tenant_slug}"
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base_url}/admin/realms",
                json={
                    "realm": realm_name,
                    "displayName": f"Haven — {tenant_slug}",
                    "enabled": True,
                    "registrationAllowed": False,
                    "loginWithEmailAllowed": True,
                    "duplicateEmailsAllowed": False,
                    "sslRequired": "external",
                    "bruteForceProtected": True,
                    "accessTokenLifespan": 3600,
                    "ssoSessionIdleTimeout": 28800,
                    "ssoSessionMaxLifespan": 28800,
                    "offlineSessionMaxLifespan": 604800,
                    "offlineSessionIdleTimeout": 172800,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 409:
                logger.info("Realm %s already exists — skipping", realm_name)
                return
            resp.raise_for_status()
        logger.info("Created Keycloak realm: %s", realm_name)

    async def delete_realm(self, tenant_slug: str) -> None:
        """Delete the tenant's Keycloak realm.

        Idempotent — does not raise if realm does not exist.
        """
        realm_name = f"tenant-{tenant_slug}"
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                f"{self._base_url}/admin/realms/{realm_name}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 404:
                logger.info("Realm %s not found — nothing to delete", realm_name)
                return
            resp.raise_for_status()
        logger.info("Deleted Keycloak realm: %s", realm_name)

    # ------------------------------------------------------------------
    # OIDC client
    # ------------------------------------------------------------------

    async def create_client(
        self,
        tenant_slug: str,
        client_id: str,
        redirect_uris: list[str],
    ) -> None:
        """Create an OIDC client in the tenant's realm.

        Idempotent — does not raise if client already exists.
        """
        realm_name = f"tenant-{tenant_slug}"
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base_url}/admin/realms/{realm_name}/clients",
                json={
                    "clientId": client_id,
                    "enabled": True,
                    "protocol": "openid-connect",
                    "publicClient": False,
                    "standardFlowEnabled": True,
                    "directAccessGrantsEnabled": False,
                    "redirectUris": redirect_uris,
                    "webOrigins": ["+"],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 409:
                logger.info("Client %s in realm %s already exists — skipping", client_id, realm_name)
                return
            resp.raise_for_status()
        logger.info("Created OIDC client %s in realm %s", client_id, realm_name)

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

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Return True if the Keycloak Admin API is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/realms/master")
                return resp.status_code == 200
        except Exception:
            return False


# Singleton instance — same pattern as k8s_client
keycloak_service = KeycloakService()
