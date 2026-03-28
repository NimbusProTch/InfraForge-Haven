import base64
import json
import logging

from kubernetes import client as k8s_lib
from kubernetes.client.exceptions import ApiException

from app.config import settings
from app.k8s.client import K8sClient

logger = logging.getLogger(__name__)

# CiliumNetworkPolicy: deny all ingress except from same tenant namespace
_CILIUM_NETPOL_TEMPLATE = {
    "apiVersion": "cilium.io/v2",
    "kind": "CiliumNetworkPolicy",
    "metadata": {"name": "tenant-isolation"},
    "spec": {
        "endpointSelector": {},
        "ingress": [
            {
                # Allow intra-tenant traffic
                "fromEndpoints": [
                    {"matchLabels": {"io.kubernetes.pod.namespace": ""}},  # filled at runtime
                ]
            },
            {
                # Allow Cilium Gateway and platform system namespaces
                "fromEntities": ["host", "cluster"],
            },
        ],
    },
}


class TenantService:
    """Handles Kubernetes provisioning for tenant lifecycle."""

    def __init__(self, k8s: K8sClient) -> None:
        self.k8s = k8s

    async def provision(
        self,
        *,
        slug: str,
        namespace: str,
        cpu_limit: str,
        memory_limit: str,
        storage_limit: str,
    ) -> None:
        """Create namespace, ResourceQuota, LimitRange, NetworkPolicy, RBAC for a new tenant."""
        if not self.k8s.is_available():
            logger.warning("K8s unavailable — skipping provisioning for tenant %s", slug)
            return

        await self._create_namespace(namespace, slug)
        await self._create_resource_quota(namespace, cpu_limit, memory_limit, storage_limit)
        await self._create_limit_range(namespace)
        await self._create_network_policy(namespace)
        await self._create_rbac(namespace, slug)
        await self._create_harbor_registry_secret(namespace)
        logger.info("Tenant %s provisioned in namespace %s", slug, namespace)

    async def deprovision(self, namespace: str) -> None:
        """Delete tenant namespace (cascades everything inside)."""
        if not self.k8s.is_available() or self.k8s.core_v1 is None:
            return
        try:
            self.k8s.core_v1.delete_namespace(namespace)
            logger.info("Namespace %s deleted", namespace)
        except ApiException as e:
            if e.status != 404:
                raise

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
                },
            )
        )
        try:
            self.k8s.core_v1.create_namespace(ns)
        except ApiException as e:
            if e.status != 409:  # 409 = already exists
                raise

    async def _create_resource_quota(
        self, namespace: str, cpu: str, memory: str, storage: str
    ) -> None:
        assert self.k8s.core_v1 is not None
        quota = k8s_lib.V1ResourceQuota(
            metadata=k8s_lib.V1ObjectMeta(name="tenant-quota"),
            spec=k8s_lib.V1ResourceQuotaSpec(
                hard={
                    "requests.cpu": cpu,
                    "limits.cpu": cpu,
                    "requests.memory": memory,
                    "limits.memory": memory,
                    "requests.storage": storage,
                    "persistentvolumeclaims": "20",
                    "pods": "50",
                    "services": "20",
                }
            ),
        )
        try:
            self.k8s.core_v1.create_namespaced_resource_quota(namespace, quota)
        except ApiException as e:
            if e.status != 409:
                raise

    async def _create_limit_range(self, namespace: str) -> None:
        assert self.k8s.core_v1 is not None
        lr = k8s_lib.V1LimitRange(
            metadata=k8s_lib.V1ObjectMeta(name="tenant-limits"),
            spec=k8s_lib.V1LimitRangeSpec(
                limits=[
                    k8s_lib.V1LimitRangeItem(
                        type="Container",
                        default={"cpu": "500m", "memory": "512Mi"},
                        default_request={"cpu": "100m", "memory": "128Mi"},
                        max={"cpu": "4", "memory": "8Gi"},
                    )
                ]
            ),
        )
        try:
            self.k8s.core_v1.create_namespaced_limit_range(namespace, lr)
        except ApiException as e:
            if e.status != 409:
                raise

    async def _create_network_policy(self, namespace: str) -> None:
        """Apply CiliumNetworkPolicy via custom objects API for L7 isolation."""
        if self.k8s.custom_objects is None:
            return
        import copy

        policy = copy.deepcopy(_CILIUM_NETPOL_TEMPLATE)
        policy["metadata"]["namespace"] = namespace
        # Allow traffic only from pods in the same namespace
        policy["spec"]["ingress"][0]["fromEndpoints"][0]["matchLabels"][
            "io.kubernetes.pod.namespace"
        ] = namespace
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
                # CRD not installed (e.g. local dev without Cilium) — skip gracefully
                logger.warning("CiliumNetworkPolicy CRD not found, skipping network policy for %s", namespace)
            elif e.status != 409:
                raise

    async def _create_harbor_registry_secret(self, namespace: str) -> None:
        """Create Harbor registry pull secret in the tenant namespace."""
        assert self.k8s.core_v1 is not None
        harbor_url = settings.harbor_url.rstrip("/")
        # Extract hostname from URL for docker config key
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
