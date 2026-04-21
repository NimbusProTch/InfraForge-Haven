"""Secret service: manages sensitive environment variables.

Design:
  - Non-sensitive env vars → GitOps values.yaml (plaintext, version-controlled).
  - Sensitive env vars → Vault (when configured) or K8s Secret (fallback).

When Vault is configured (VAULT_URL + VAULT_TOKEN):
  - Sensitive vars written to Vault KV v2: haven/tenants/{tenant}/apps/{app}/secrets
  - ESO (External Secrets Operator) syncs Vault → K8s Secret automatically
  - Pod reads via envFrom.secretRef (same as before)

When Vault is NOT configured:
  - Falls back to direct K8s Secret management (legacy behavior)

K8s Secret naming convention:
  {app_slug}-env-secrets  (e.g. "my-api-env-secrets")
"""

import base64
import logging

from kubernetes.client.exceptions import ApiException

from app.k8s.client import K8sClient

logger = logging.getLogger(__name__)

_LABEL_MANAGED_BY = "haven"

# ClusterSecretStore + ESO apiVersion pinned by platform/argocd/apps/platform/
# external-secrets-config/cluster-secret-store.yaml (2.V.2). If these drift from
# that manifest, ESO cannot find the store and ExternalSecret reconciliation
# silently fails. Locked by api/tests/test_secret_service_constants.py.
_CLUSTER_SECRET_STORE_NAME = "vault-backend"
_ESO_API_VERSION = "external-secrets.io/v1beta1"
_ESO_CRD_VERSION = "v1beta1"


def _secret_name(app_slug: str) -> str:
    """Canonical K8s Secret name for an app's sensitive env vars."""
    return f"{app_slug}-env-secrets"


def _build_secret_body(namespace: str, app_slug: str, data: dict[str, str]) -> dict:
    """Build a K8s Secret manifest for sensitive env vars."""
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": _secret_name(app_slug),
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/managed-by": _LABEL_MANAGED_BY,
                "haven.io/app": app_slug,
                "haven.io/secret-type": "env-vars",
            },
        },
        "type": "Opaque",
        # stringData → K8s auto-base64-encodes; safe for UTF-8 values
        "stringData": data,
    }


class SecretService:
    """Creates, updates, and deletes secrets for sensitive env vars.

    Uses Vault when configured (VAULT_URL set), falls back to direct K8s Secrets.
    """

    def __init__(self, k8s: K8sClient) -> None:
        self._k8s = k8s
        from app.services.vault_service import vault_service

        self._vault = vault_service

    def uses_vault(self) -> bool:
        """Return True if Vault is configured and will be used for secret storage."""
        return self._vault.is_configured()

    async def upsert_sensitive_vars(
        self,
        namespace: str,
        app_slug: str,
        tenant_slug: str,
        data: dict[str, str],
    ) -> bool:
        """Write sensitive env vars. Uses Vault if configured, K8s Secret otherwise.

        When using Vault, also creates an ExternalSecret CRD so ESO syncs to K8s.
        Returns True on success.
        """
        if self.uses_vault():
            await self._vault.write_secrets(tenant_slug, app_slug, data)
            self._ensure_external_secret(namespace, app_slug, tenant_slug)
            return True
        return self.upsert_secret(namespace, app_slug, data)

    async def delete_sensitive_vars(self, namespace: str, app_slug: str, tenant_slug: str) -> bool:
        """Delete sensitive env vars from Vault or K8s Secret."""
        if self.uses_vault():
            await self._vault.delete_secrets(tenant_slug, app_slug)
            self._delete_external_secret(namespace, app_slug)
            return True
        return self.delete_secret(namespace, app_slug)

    def _ensure_external_secret(self, namespace: str, app_slug: str, tenant_slug: str) -> None:
        """Create/update ExternalSecret CRD so ESO syncs Vault → K8s Secret."""
        if not self._k8s.is_available() or self._k8s.custom_objects is None:
            return

        body = {
            "apiVersion": _ESO_API_VERSION,
            "kind": "ExternalSecret",
            "metadata": {
                "name": _secret_name(app_slug),
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": _LABEL_MANAGED_BY,
                    "haven.io/app": app_slug,
                },
            },
            "spec": {
                "refreshInterval": "30s",
                "secretStoreRef": {"name": _CLUSTER_SECRET_STORE_NAME, "kind": "ClusterSecretStore"},
                "target": {"name": _secret_name(app_slug), "creationPolicy": "Owner"},
                "dataFrom": [{"extract": {"key": f"tenants/{tenant_slug}/apps/{app_slug}/secrets"}}],
            },
        }

        try:
            self._k8s.custom_objects.create_namespaced_custom_object(
                group="external-secrets.io",
                version=_ESO_CRD_VERSION,
                namespace=namespace,
                plural="externalsecrets",
                body=body,
            )
        except ApiException as e:
            if e.status == 409:
                self._k8s.custom_objects.replace_namespaced_custom_object(
                    group="external-secrets.io",
                    version=_ESO_CRD_VERSION,
                    namespace=namespace,
                    plural="externalsecrets",
                    name=_secret_name(app_slug),
                    body=body,
                )
            else:
                raise

    def _delete_external_secret(self, namespace: str, app_slug: str) -> None:
        """Delete ExternalSecret CRD."""
        if not self._k8s.is_available() or self._k8s.custom_objects is None:
            return
        try:
            self._k8s.custom_objects.delete_namespaced_custom_object(
                group="external-secrets.io",
                version=_ESO_CRD_VERSION,
                namespace=namespace,
                plural="externalsecrets",
                name=_secret_name(app_slug),
            )
        except ApiException as e:
            if e.status != 404:
                raise

    def _core(self):
        return self._k8s.core_v1

    def _available(self) -> bool:
        return self._k8s.is_available() and self._core() is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_secret(self, namespace: str, app_slug: str, data: dict[str, str]) -> bool:
        """Create a new K8s Secret for an app's sensitive env vars.

        Returns True on success, False if K8s is unavailable.
        Raises ApiException on conflict (409) so callers can decide to upsert.
        """
        if not self._available():
            logger.warning("K8s unavailable — cannot create secret for app %s", app_slug)
            return False

        body = _build_secret_body(namespace, app_slug, data)
        self._core().create_namespaced_secret(namespace=namespace, body=body)
        logger.info("Created secret %s in %s", _secret_name(app_slug), namespace)
        return True

    def update_secret(self, namespace: str, app_slug: str, data: dict[str, str]) -> bool:
        """Replace (PUT) a K8s Secret with new data.

        Returns True on success, False if K8s is unavailable.
        """
        if not self._available():
            logger.warning("K8s unavailable — cannot update secret for app %s", app_slug)
            return False

        body = _build_secret_body(namespace, app_slug, data)
        self._core().replace_namespaced_secret(
            name=_secret_name(app_slug),
            namespace=namespace,
            body=body,
        )
        logger.info("Updated secret %s in %s", _secret_name(app_slug), namespace)
        return True

    def upsert_secret(self, namespace: str, app_slug: str, data: dict[str, str]) -> bool:
        """Create or replace a K8s Secret — idempotent.

        Returns True on success, False if K8s is unavailable.
        """
        if not self._available():
            logger.warning("K8s unavailable — cannot upsert secret for app %s", app_slug)
            return False

        try:
            return self.create_secret(namespace, app_slug, data)
        except ApiException as exc:
            if exc.status == 409:
                # Already exists — replace it
                return self.update_secret(namespace, app_slug, data)
            raise

    def delete_secret(self, namespace: str, app_slug: str) -> bool:
        """Delete the K8s Secret for an app.

        Returns True on success (including 404 — idempotent).
        Returns False if K8s is unavailable.
        """
        if not self._available():
            logger.warning("K8s unavailable — cannot delete secret for app %s", app_slug)
            return False

        try:
            self._core().delete_namespaced_secret(
                name=_secret_name(app_slug),
                namespace=namespace,
            )
            logger.info("Deleted secret %s in %s", _secret_name(app_slug), namespace)
            return True
        except ApiException as exc:
            if exc.status == 404:
                logger.debug("Secret %s not found in %s — already deleted", _secret_name(app_slug), namespace)
                return True
            raise

    def list_secret_keys(self, namespace: str, app_slug: str) -> list[str]:
        """Return the list of keys stored in the secret (values are never returned).

        Returns empty list if secret does not exist or K8s is unavailable.
        """
        if not self._available():
            return []

        try:
            secret = self._core().read_namespaced_secret(
                name=_secret_name(app_slug),
                namespace=namespace,
            )
            # .data contains base64-encoded values; we only expose keys
            raw_data: dict | None = secret.data
            if not raw_data:
                return []
            return list(raw_data.keys())
        except ApiException as exc:
            if exc.status == 404:
                return []
            raise

    def secret_name_for(self, app_slug: str) -> str:
        """Return the K8s Secret name for the given app slug."""
        return _secret_name(app_slug)

    def decode_secret_data(self, encoded: dict[str, str]) -> dict[str, str]:
        """Decode base64-encoded secret .data values to plaintext strings.

        Useful when reading back a secret for rotation/merge operations.
        """
        return {k: base64.b64decode(v).decode("utf-8") for k, v in encoded.items()}
