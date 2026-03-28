import base64
import json
import logging

from kubernetes import client as k8s_lib
from kubernetes.client.exceptions import ApiException

from app.config import settings
from app.k8s.client import K8sClient
from app.services.harbor_service import HarborService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier-based resource defaults
# ---------------------------------------------------------------------------

_TIER_QUOTAS: dict[str, dict[str, str]] = {
    "free": {"pods": "10", "persistentvolumeclaims": "3", "services": "5"},
    "dev": {"pods": "20", "persistentvolumeclaims": "5", "services": "10"},
    "starter": {"pods": "20", "persistentvolumeclaims": "5", "services": "10"},
    "standard": {"pods": "50", "persistentvolumeclaims": "20", "services": "20"},
    "pro": {"pods": "50", "persistentvolumeclaims": "20", "services": "20"},
    "premium": {"pods": "200", "persistentvolumeclaims": "100", "services": "50"},
    "enterprise": {"pods": "200", "persistentvolumeclaims": "100", "services": "50"},
}

_TIER_PVC_MAX: dict[str, str] = {
    "free": "50Gi",
    "dev": "50Gi",
    "starter": "50Gi",
    "standard": "200Gi",
    "pro": "200Gi",
    "premium": "1Ti",
    "enterprise": "1Ti",
}

_DEFAULT_TIER = "free"

# ---------------------------------------------------------------------------
# CiliumNetworkPolicy: L7-aware tenant isolation
# ---------------------------------------------------------------------------
# Design:
#   Ingress: allow same-namespace, haven-system (API), monitoring (Prometheus)
#   Egress: allow same-namespace, kube-dns (port 53), external internet (world entity)
#   Everything else is denied by default (Cilium default-deny when CNP is present)
# ---------------------------------------------------------------------------

_CILIUM_NETPOL_TEMPLATE: dict = {
    "apiVersion": "cilium.io/v2",
    "kind": "CiliumNetworkPolicy",
    "metadata": {"name": "tenant-isolation"},
    "spec": {
        "endpointSelector": {},
        "ingress": [
            {
                # Intra-tenant: pods within the same namespace can reach each other
                "fromEndpoints": [
                    {"matchLabels": {"io.kubernetes.pod.namespace": "__NAMESPACE__"}}
                ]
            },
            {
                # Haven API (haven-system) → tenant pods (deployment, health checks)
                "fromEndpoints": [
                    {"matchLabels": {"io.kubernetes.pod.namespace": "haven-system"}}
                ]
            },
            {
                # Prometheus (monitoring namespace) → tenant pod /metrics scraping
                "fromEndpoints": [
                    {"matchLabels": {"io.kubernetes.pod.namespace": "monitoring"}}
                ]
            },
        ],
        "egress": [
            {
                # Intra-tenant: pods can talk to each other within same namespace
                "toEndpoints": [
                    {"matchLabels": {"io.kubernetes.pod.namespace": "__NAMESPACE__"}}
                ]
            },
            {
                # DNS resolution via kube-dns in kube-system
                "toEndpoints": [
                    {"matchLabels": {"io.kubernetes.pod.namespace": "kube-system"}}
                ],
                "toPorts": [
                    {
                        "ports": [
                            {"port": "53", "protocol": "UDP"},
                            {"port": "53", "protocol": "TCP"},
                        ]
                    }
                ],
            },
            {
                # Internet egress (world entity = external IPs, excludes cluster pods)
                # This allows apps to reach external APIs, package registries, etc.
                "toEntities": ["world"]
            },
        ],
    },
}


class TenantService:
    """Handles Kubernetes provisioning for tenant lifecycle."""

    def __init__(self, k8s: K8sClient, harbor: HarborService | None = None) -> None:
        self.k8s = k8s
        self.harbor = harbor or HarborService()

    async def provision(
        self,
        *,
        slug: str,
        namespace: str,
        cpu_limit: str,
        memory_limit: str,
        storage_limit: str,
        tier: str = _DEFAULT_TIER,
    ) -> None:
        """Create namespace, ResourceQuota, LimitRange, NetworkPolicy, RBAC for a new tenant.

        Provisioning order (IS1-04):
          1. Namespace (with PSA label: restricted)
          2. ResourceQuota (tier-based)
          3. LimitRange (tier-based)
          4. CiliumNetworkPolicy
          5. Haven system ServiceAccount + RBAC
          6. Harbor registry pull secret
        """
        if not self.k8s.is_available():
            logger.warning("K8s unavailable — skipping provisioning for tenant %s", slug)
            return

        await self._create_namespace(namespace, slug)
        await self._create_resource_quota(namespace, cpu_limit, memory_limit, storage_limit, tier)
        await self._create_limit_range(namespace, tier)
        await self._create_network_policy(namespace)
        await self._create_rbac(namespace, slug)
        await self._create_harbor_registry_secret(namespace)
        await self._provision_harbor_project(slug, namespace, tier)
        logger.info("Tenant %s provisioned in namespace %s (tier=%s)", slug, namespace, tier)

    async def deprovision(self, namespace: str, slug: str | None = None) -> None:
        """Delete tenant namespace and Harbor project."""
        if not self.k8s.is_available() or self.k8s.core_v1 is None:
            return
        try:
            self.k8s.core_v1.delete_namespace(namespace)
            logger.info("Namespace %s deleted", namespace)
        except ApiException as e:
            if e.status != 404:
                raise

        # Clean up Harbor project (non-blocking — log on failure, don't abort)
        if slug:
            try:
                await self.harbor.delete_project(slug)
            except Exception as exc:
                logger.warning("Harbor project deletion failed for tenant %s: %s", slug, exc)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _create_namespace(self, namespace: str, slug: str) -> None:
        assert self.k8s.core_v1 is not None
        ns = k8s_lib.V1Namespace(
            metadata=k8s_lib.V1ObjectMeta(
                name=namespace,
                labels={
                    "haven.io/tenant": slug,
                    "haven.io/managed": "true",
                    # Pod Security Admission: enforce restricted profile
                    "pod-security.kubernetes.io/enforce": "restricted",
                    "pod-security.kubernetes.io/enforce-version": "latest",
                    "pod-security.kubernetes.io/warn": "restricted",
                    "pod-security.kubernetes.io/warn-version": "latest",
                },
            )
        )
        try:
            self.k8s.core_v1.create_namespace(ns)
        except ApiException as e:
            if e.status != 409:  # 409 = already exists
                raise

    async def _create_resource_quota(
        self, namespace: str, cpu: str, memory: str, storage: str, tier: str
    ) -> None:
        assert self.k8s.core_v1 is not None
        tier_defaults = _TIER_QUOTAS.get(tier, _TIER_QUOTAS[_DEFAULT_TIER])
        quota = k8s_lib.V1ResourceQuota(
            metadata=k8s_lib.V1ObjectMeta(name="tenant-quota"),
            spec=k8s_lib.V1ResourceQuotaSpec(
                hard={
                    "requests.cpu": cpu,
                    "limits.cpu": cpu,
                    "requests.memory": memory,
                    "limits.memory": memory,
                    "requests.storage": storage,
                    "pods": tier_defaults["pods"],
                    "persistentvolumeclaims": tier_defaults["persistentvolumeclaims"],
                    "services": tier_defaults["services"],
                }
            ),
        )
        try:
            self.k8s.core_v1.create_namespaced_resource_quota(namespace, quota)
        except ApiException as e:
            if e.status == 409:
                # Idempotent: update existing quota (e.g. tier change)
                self.k8s.core_v1.replace_namespaced_resource_quota(namespace=namespace, name="tenant-quota", body=quota)
            else:
                raise

    async def _create_limit_range(self, namespace: str, tier: str) -> None:
        assert self.k8s.core_v1 is not None
        pvc_max = _TIER_PVC_MAX.get(tier, _TIER_PVC_MAX[_DEFAULT_TIER])
        lr = k8s_lib.V1LimitRange(
            metadata=k8s_lib.V1ObjectMeta(name="tenant-limits"),
            spec=k8s_lib.V1LimitRangeSpec(
                limits=[
                    k8s_lib.V1LimitRangeItem(
                        type="Container",
                        default={"cpu": "500m", "memory": "512Mi"},
                        default_request={"cpu": "100m", "memory": "128Mi"},
                        min={"cpu": "10m", "memory": "32Mi"},
                        max={"cpu": "4", "memory": "4Gi"},
                    ),
                    k8s_lib.V1LimitRangeItem(
                        type="PersistentVolumeClaim",
                        min={"storage": "1Gi"},
                        max={"storage": pvc_max},
                    ),
                ]
            ),
        )
        try:
            self.k8s.core_v1.create_namespaced_limit_range(namespace, lr)
        except ApiException as e:
            if e.status == 409:
                self.k8s.core_v1.replace_namespaced_limit_range(namespace=namespace, name="tenant-limits", body=lr)
            else:
                raise

    async def _create_network_policy(self, namespace: str) -> None:
        """Apply CiliumNetworkPolicy via custom objects API for L7 isolation."""
        if self.k8s.custom_objects is None:
            return
        import json as _json

        # Deep-copy and substitute __NAMESPACE__ placeholder in one pass
        policy_str = _json.dumps(_CILIUM_NETPOL_TEMPLATE).replace("__NAMESPACE__", namespace)
        policy = _json.loads(policy_str)
        policy["metadata"]["namespace"] = namespace

        try:
            self.k8s.custom_objects.create_namespaced_custom_object(
                group="cilium.io",
                version="v2",
                namespace=namespace,
                plural="ciliumnetworkpolicies",
                body=policy,
            )
        except ApiException as e:
            if e.status == 404:
                logger.warning("CiliumNetworkPolicy CRD not found, skipping network policy for %s", namespace)
            elif e.status != 409:
                raise

    async def _create_harbor_registry_secret(self, namespace: str) -> None:
        """Create Harbor registry pull secret in the tenant namespace."""
        assert self.k8s.core_v1 is not None
        harbor_url = settings.harbor_url.rstrip("/")
        from urllib.parse import urlparse

        harbor_host = urlparse(harbor_url).netloc or harbor_url
        docker_config = {
            "auths": {
                harbor_host: {
                    "auth": base64.b64encode(f"admin:{settings.harbor_admin_password}".encode()).decode()
                }
            }
        }
        secret = k8s_lib.V1Secret(
            metadata=k8s_lib.V1ObjectMeta(name="harbor-registry-secret"),
            type="kubernetes.io/dockerconfigjson",
            data={".dockerconfigjson": base64.b64encode(json.dumps(docker_config).encode()).decode()},
        )
        try:
            self.k8s.core_v1.create_namespaced_secret(namespace, secret)
        except ApiException as e:
            if e.status != 409:
                raise

    async def _create_rbac(self, namespace: str, slug: str) -> None:
        """Create Role/RoleBinding for three OIDC groups: admin, developer, viewer.

        Group naming convention (IS4-02):
          Keycloak group:  tenant_{slug}_{role}
          K8s subject:     oidc:tenant_{slug}_{role}   (oidc: prefix from kube-apiserver --oidc-groups-prefix)
        """
        assert self.k8s.rbac_v1 is not None

        manage_verbs = ["get", "list", "watch", "create", "update", "patch", "delete"]
        read_verbs = ["get", "list", "watch"]

        roles_and_bindings: list[tuple] = [
            # --- admin: full workload + service management ---
            (
                k8s_lib.V1Role(
                    metadata=k8s_lib.V1ObjectMeta(name="haven-tenant-admin", namespace=namespace),
                    rules=[
                        k8s_lib.V1PolicyRule(
                            api_groups=["", "apps", "batch", "autoscaling"],
                            resources=[
                                "pods", "pods/log", "pods/exec", "pods/portforward",
                                "deployments", "statefulsets", "replicasets",
                                "jobs", "cronjobs", "horizontalpodautoscalers",
                                "services", "endpoints", "configmaps",
                                "persistentvolumeclaims", "events",
                            ],
                            verbs=manage_verbs,
                        ),
                        # Secrets: read-only (prevent exfiltration of cluster secrets)
                        k8s_lib.V1PolicyRule(
                            api_groups=[""],
                            resources=["secrets"],
                            verbs=read_verbs,
                        ),
                        k8s_lib.V1PolicyRule(
                            api_groups=["gateway.networking.k8s.io"],
                            resources=["httproutes", "grpcroutes", "tcproutes"],
                            verbs=manage_verbs,
                        ),
                    ],
                ),
                k8s_lib.V1RoleBinding(
                    metadata=k8s_lib.V1ObjectMeta(name="haven-tenant-admin-binding", namespace=namespace),
                    subjects=[
                        k8s_lib.RbacV1Subject(
                            kind="Group",
                            # oidc: prefix matches --oidc-groups-prefix on kube-apiserver (IS4-01)
                            name=f"oidc:tenant_{slug}_admin",
                            api_group="rbac.authorization.k8s.io",
                        )
                    ],
                    role_ref=k8s_lib.V1RoleRef(
                        kind="Role",
                        name="haven-tenant-admin",
                        api_group="rbac.authorization.k8s.io",
                    ),
                ),
            ),
            # --- developer: deploy + read (no infra management) ---
            (
                k8s_lib.V1Role(
                    metadata=k8s_lib.V1ObjectMeta(name="haven-tenant-developer", namespace=namespace),
                    rules=[
                        k8s_lib.V1PolicyRule(
                            api_groups=["", "apps", "batch", "autoscaling"],
                            resources=[
                                "pods", "pods/log", "deployments", "statefulsets",
                                "replicasets", "jobs", "cronjobs",
                                "horizontalpodautoscalers", "services",
                                "endpoints", "configmaps", "events",
                                "persistentvolumeclaims",
                            ],
                            verbs=read_verbs,
                        ),
                        k8s_lib.V1PolicyRule(
                            api_groups=[""],
                            resources=["pods/exec", "pods/portforward"],
                            verbs=["create"],
                        ),
                        k8s_lib.V1PolicyRule(
                            api_groups=["apps"],
                            resources=["deployments"],
                            verbs=["get", "list", "watch", "update", "patch"],
                        ),
                        k8s_lib.V1PolicyRule(
                            api_groups=[""],
                            resources=["configmaps"],
                            verbs=manage_verbs,
                        ),
                    ],
                ),
                k8s_lib.V1RoleBinding(
                    metadata=k8s_lib.V1ObjectMeta(name="haven-tenant-developer-binding", namespace=namespace),
                    subjects=[
                        k8s_lib.RbacV1Subject(
                            kind="Group",
                            name=f"oidc:tenant_{slug}_developer",
                            api_group="rbac.authorization.k8s.io",
                        )
                    ],
                    role_ref=k8s_lib.V1RoleRef(
                        kind="Role",
                        name="haven-tenant-developer",
                        api_group="rbac.authorization.k8s.io",
                    ),
                ),
            ),
            # --- viewer: read-only ---
            (
                k8s_lib.V1Role(
                    metadata=k8s_lib.V1ObjectMeta(name="haven-tenant-viewer", namespace=namespace),
                    rules=[
                        k8s_lib.V1PolicyRule(
                            api_groups=["", "apps", "batch", "autoscaling"],
                            resources=[
                                "pods", "pods/log", "deployments", "statefulsets",
                                "replicasets", "jobs", "cronjobs",
                                "horizontalpodautoscalers", "services",
                                "endpoints", "configmaps", "events",
                                "persistentvolumeclaims",
                            ],
                            verbs=read_verbs,
                        ),
                        k8s_lib.V1PolicyRule(
                            api_groups=["gateway.networking.k8s.io"],
                            resources=["httproutes"],
                            verbs=read_verbs,
                        ),
                    ],
                ),
                k8s_lib.V1RoleBinding(
                    metadata=k8s_lib.V1ObjectMeta(name="haven-tenant-viewer-binding", namespace=namespace),
                    subjects=[
                        k8s_lib.RbacV1Subject(
                            kind="Group",
                            name=f"oidc:tenant_{slug}_viewer",
                            api_group="rbac.authorization.k8s.io",
                        )
                    ],
                    role_ref=k8s_lib.V1RoleRef(
                        kind="Role",
                        name="haven-tenant-viewer",
                        api_group="rbac.authorization.k8s.io",
                    ),
                ),
            ),
        ]

        for role, rb in roles_and_bindings:
            for create_fn, obj in [
                (self.k8s.rbac_v1.create_namespaced_role, role),
                (self.k8s.rbac_v1.create_namespaced_role_binding, rb),
            ]:
                try:
                    create_fn(namespace, obj)
                except ApiException as e:
                    if e.status != 409:
                        raise

    async def _provision_harbor_project(self, slug: str, namespace: str, tier: str) -> None:
        """Create Harbor project + robot account + per-tenant imagePullSecret.

        Non-blocking: errors are logged but do not abort tenant provisioning.
        The admin pull secret (harbor-registry-secret) is still created by
        _create_harbor_registry_secret for build pipeline compatibility.
        """
        if self.k8s.core_v1 is None:
            return
        try:
            await self.harbor.create_project(slug, tier)
            creds = await self.harbor.create_robot_account(slug)
            secret_manifest = self.harbor.build_imagepull_secret(slug, creds)
            # Create K8s secret in tenant namespace
            secret = k8s_lib.V1Secret(
                metadata=k8s_lib.V1ObjectMeta(
                    name=secret_manifest["metadata"]["name"],
                    namespace=namespace,
                ),
                type=secret_manifest["type"],
                data=secret_manifest["data"],
            )
            try:
                self.k8s.core_v1.create_namespaced_secret(namespace, secret)
            except ApiException as e:
                if e.status == 409:
                    self.k8s.core_v1.replace_namespaced_secret(
                        namespace=namespace, name=secret_manifest["metadata"]["name"], body=secret
                    )
                else:
                    raise
            logger.info("Harbor project + robot account provisioned for tenant %s", slug)
        except Exception as exc:
            logger.warning("Harbor provisioning failed for tenant %s (non-fatal): %s", slug, exc)
