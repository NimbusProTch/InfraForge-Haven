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

    # ------------------------------------------------------------------
    # Tenant groups (shared "haven" realm) — H1a-2 kubectl OIDC
    # ------------------------------------------------------------------
    #
    # The cluster's kube-apiserver is configured with `--oidc-groups-claim=groups`
    # and `--oidc-groups-prefix=oidc:`. tenant_service.py creates per-tenant
    # RoleBindings against subjects like `oidc:tenant_{slug}_admin`. For those
    # bindings to actually grant access, the user's Keycloak token must carry a
    # `groups` claim that includes `tenant_{slug}_admin`.
    #
    # The methods below manage the **groups** in the shared `haven` realm
    # (NOT per-tenant realms — see file header comment). Each tenant gets
    # three groups: `tenant_{slug}_admin`, `tenant_{slug}_developer`,
    # `tenant_{slug}_viewer`. Users are added to the appropriate group when
    # the platform invites them as a tenant member.

    _TENANT_ROLES = ("admin", "developer", "viewer")

    def _tenant_group_name(self, tenant_slug: str, role: str) -> str:
        """Return the canonical group name. Mirrored by `tenant_service.py:395`."""
        return f"tenant_{tenant_slug}_{role}"

    async def create_tenant_groups(self, tenant_slug: str) -> dict[str, str]:
        """Create the three tenant role groups in the shared `haven` realm.

        Idempotent — if a group already exists (409 Conflict), the existing
        ID is fetched and returned.

        Returns: ``{role: group_id}`` mapping for the three roles.
        """
        realm = settings.keycloak_realm  # shared "haven" realm
        token = await self._get_admin_token()
        result: dict[str, str] = {}

        async with httpx.AsyncClient(timeout=15) as client:
            for role in self._TENANT_ROLES:
                group_name = self._tenant_group_name(tenant_slug, role)
                create_resp = await client.post(
                    f"{self._base_url}/admin/realms/{realm}/groups",
                    json={"name": group_name},
                    headers={"Authorization": f"Bearer {token}"},
                )
                if create_resp.status_code == 201:
                    location = create_resp.headers.get("Location", "")
                    group_id = location.rsplit("/", 1)[-1]
                    logger.info("Created Keycloak group %s in realm %s (id=%s)", group_name, realm, group_id)
                elif create_resp.status_code == 409:
                    # Already exists — find by name
                    search_resp = await client.get(
                        f"{self._base_url}/admin/realms/{realm}/groups",
                        params={"search": group_name, "exact": "true"},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    search_resp.raise_for_status()
                    groups = search_resp.json()
                    matches = [g for g in groups if g.get("name") == group_name]
                    if not matches:
                        logger.warning(
                            "Group %s reported as 409 conflict but not found in search results",
                            group_name,
                        )
                        continue
                    group_id = matches[0]["id"]
                    logger.debug("Keycloak group %s already exists (id=%s)", group_name, group_id)
                else:
                    create_resp.raise_for_status()
                    continue
                result[role] = group_id

        return result

    async def delete_tenant_groups(self, tenant_slug: str) -> None:
        """Remove the three tenant role groups from the shared `haven` realm.

        Best-effort — missing groups (404) are logged but do not raise. This
        runs as part of tenant deprovision and must not block the rest of
        the cleanup chain.
        """
        realm = settings.keycloak_realm
        token = await self._get_admin_token()

        async with httpx.AsyncClient(timeout=15) as client:
            for role in self._TENANT_ROLES:
                group_name = self._tenant_group_name(tenant_slug, role)
                # Find the group ID first
                search_resp = await client.get(
                    f"{self._base_url}/admin/realms/{realm}/groups",
                    params={"search": group_name, "exact": "true"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                if search_resp.status_code != 200:
                    logger.warning("Failed to search for group %s: %s", group_name, search_resp.status_code)
                    continue
                groups = search_resp.json()
                matches = [g for g in groups if g.get("name") == group_name]
                if not matches:
                    logger.debug("Group %s not found during cleanup, skipping", group_name)
                    continue
                group_id = matches[0]["id"]
                del_resp = await client.delete(
                    f"{self._base_url}/admin/realms/{realm}/groups/{group_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if del_resp.status_code in (204, 404):
                    logger.info("Deleted Keycloak group %s (id=%s)", group_name, group_id)
                else:
                    logger.warning(
                        "Failed to delete group %s: status=%s body=%s",
                        group_name,
                        del_resp.status_code,
                        del_resp.text[:200],
                    )

    async def add_user_to_tenant_group(
        self,
        user_id: str,
        tenant_slug: str,
        role: str,
    ) -> bool:
        """Add a Keycloak user to the `tenant_{slug}_{role}` group.

        Returns ``True`` if the assignment was made (or already in place),
        ``False`` if the user or group could not be found. Best-effort: a
        failure here means the user has a working tenant DB membership but
        cannot use kubectl until manual fix.
        """
        if role not in self._TENANT_ROLES:
            logger.warning("Unknown tenant role %r — must be one of %s", role, self._TENANT_ROLES)
            return False
        if not user_id:
            logger.debug("Skipping group add: empty user_id (Keycloak user not yet created)")
            return False

        realm = settings.keycloak_realm
        token = await self._get_admin_token()
        group_name = self._tenant_group_name(tenant_slug, role)

        async with httpx.AsyncClient(timeout=15) as client:
            # Find the group ID
            search_resp = await client.get(
                f"{self._base_url}/admin/realms/{realm}/groups",
                params={"search": group_name, "exact": "true"},
                headers={"Authorization": f"Bearer {token}"},
            )
            if search_resp.status_code != 200:
                logger.warning("Group search failed for %s: %s", group_name, search_resp.status_code)
                return False
            groups = search_resp.json()
            matches = [g for g in groups if g.get("name") == group_name]
            if not matches:
                logger.warning(
                    "Group %s does not exist — was create_tenant_groups called?",
                    group_name,
                )
                return False
            group_id = matches[0]["id"]

            # PUT /users/{userId}/groups/{groupId} — idempotent
            assign_resp = await client.put(
                f"{self._base_url}/admin/realms/{realm}/users/{user_id}/groups/{group_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if assign_resp.status_code in (204, 200):
                logger.info(
                    "Added Keycloak user %s to group %s (realm=%s)",
                    user_id,
                    group_name,
                    realm,
                )
                return True
            logger.warning(
                "Failed to add user %s to group %s: status=%s",
                user_id,
                group_name,
                assign_resp.status_code,
            )
            return False


# Singleton instance — same pattern as k8s_client
keycloak_service = KeycloakService()
