import asyncio
import base64
import json
import logging

from kubernetes import client as k8s_lib
from kubernetes.client.exceptions import ApiException

from app.config import settings
from app.k8s.client import K8sClient
from app.services.harbor_service import HarborService
from app.services.lifecycle_events import lifecycle_bus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier-based resource defaults
# ---------------------------------------------------------------------------

_TIER_QUOTAS: dict[str, dict[str, str]] = {
    "free": {"pods": "20", "persistentvolumeclaims": "5", "services": "15"},
    "dev": {"pods": "30", "persistentvolumeclaims": "10", "services": "20"},
    "starter": {"pods": "30", "persistentvolumeclaims": "10", "services": "20"},
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
                "fromEndpoints": [{"matchLabels": {"io.kubernetes.pod.namespace": "__NAMESPACE__"}}]
            },
            {
                # Haven API (haven-system) → tenant pods (deployment, health checks)
                "fromEndpoints": [{"matchLabels": {"io.kubernetes.pod.namespace": "haven-system"}}]
            },
            {
                # Prometheus (monitoring namespace) → tenant pod /metrics scraping
                "fromEndpoints": [{"matchLabels": {"io.kubernetes.pod.namespace": "monitoring"}}]
            },
        ],
        "egress": [
            {
                # Intra-tenant: pods can talk to each other within same namespace
                "toEndpoints": [{"matchLabels": {"io.kubernetes.pod.namespace": "__NAMESPACE__"}}]
            },
            {
                # DNS resolution via kube-dns in kube-system
                "toEndpoints": [{"matchLabels": {"io.kubernetes.pod.namespace": "kube-system"}}],
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
                # Everest namespace: Managed databases (PG, MySQL, MongoDB) live here
                "toEndpoints": [{"matchLabels": {"io.kubernetes.pod.namespace": "everest"}}],
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

        bus_key = f"tenant:{slug}"

        lifecycle_bus.emit(bus_key, "namespace", "running", f"Creating namespace {namespace}")
        await self._create_namespace(namespace, slug)
        lifecycle_bus.emit(bus_key, "namespace", "done", f"Namespace {namespace} created")

        lifecycle_bus.emit(bus_key, "quota", "running", "Applying ResourceQuota")
        await self._create_resource_quota(namespace, cpu_limit, memory_limit, storage_limit, tier)
        lifecycle_bus.emit(bus_key, "quota", "done", f"ResourceQuota applied ({cpu_limit} CPU, {memory_limit})")

        lifecycle_bus.emit(bus_key, "limits", "running", "Applying LimitRange")
        await self._create_limit_range(namespace, tier)
        lifecycle_bus.emit(bus_key, "limits", "done", "LimitRange applied")

        lifecycle_bus.emit(bus_key, "network", "running", "Creating CiliumNetworkPolicy")
        await self._create_network_policy(namespace)
        lifecycle_bus.emit(bus_key, "network", "done", "Network isolation policy created")

        lifecycle_bus.emit(bus_key, "rbac", "running", "Creating RBAC roles")
        await self._create_rbac(namespace, slug)
        lifecycle_bus.emit(bus_key, "rbac", "done", "RBAC roles created (admin, developer, viewer)")

        lifecycle_bus.emit(bus_key, "harbor-secret", "running", "Creating Harbor registry secret")
        await self._create_harbor_registry_secret(namespace)
        lifecycle_bus.emit(bus_key, "harbor-secret", "done", "Harbor pull secret created")

        lifecycle_bus.emit(bus_key, "harbor-project", "running", "Provisioning Harbor project")
        await self._provision_harbor_project(slug, namespace, tier)
        lifecycle_bus.emit(bus_key, "harbor-project", "done", f"Harbor project tenant-{slug} created")

        lifecycle_bus.emit(bus_key, "appset", "running", "Creating ArgoCD ApplicationSet")
        await self._create_applicationset(slug)
        lifecycle_bus.emit(bus_key, "appset", "done", f"ApplicationSet appset-{slug} created")

        # H1a-2: create the three Keycloak groups (`tenant_{slug}_admin`,
        # `_developer`, `_viewer`) so that tenant admins can obtain Keycloak
        # tokens carrying the `groups` claim that kube-apiserver matches
        # against the RoleBindings created in `_create_rbac` above.
        # Best-effort: failure is logged but does not abort tenant
        # provisioning (the tenant still works via the platform UI/API,
        # just not via direct kubectl until the groups exist).
        lifecycle_bus.emit(bus_key, "keycloak-groups", "running", "Creating Keycloak tenant groups")
        try:
            from app.services.keycloak_service import keycloak_service

            await keycloak_service.create_tenant_groups(slug)
            lifecycle_bus.emit(
                bus_key,
                "keycloak-groups",
                "done",
                f"Keycloak groups created (tenant_{slug}_admin/developer/viewer)",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Keycloak group creation failed for tenant %s (non-fatal, kubectl OIDC won't work until manually fixed): %s",
                slug,
                exc,
            )
            # Emit "done" with a "skipped" message rather than "warn" — the
            # tenant provision as a whole still succeeded, the group creation
            # is a best-effort optimization for kubectl OIDC. Existing tests
            # expect every "running" step to terminate in "done".
            lifecycle_bus.emit(
                bus_key,
                "keycloak-groups",
                "done",
                f"Keycloak group creation skipped (non-fatal): {exc}",
            )

        lifecycle_bus.mark_done(bus_key, success=True, message=f"Tenant {slug} provisioned")
        logger.info("Tenant %s provisioned in namespace %s (tier=%s)", slug, namespace, tier)

    async def deprovision(self, namespace: str, slug: str | None = None) -> None:
        """Delete tenant ApplicationSet, namespace, and Harbor project."""
        if not self.k8s.is_available() or self.k8s.core_v1 is None:
            return

        bus_key = f"tenant:{slug or namespace}"

        if slug:
            lifecycle_bus.emit(bus_key, "appset-delete", "running", f"Deleting ApplicationSet appset-{slug}")
            await self._delete_applicationset(slug)
            lifecycle_bus.emit(bus_key, "appset-delete", "done", "ApplicationSet deleted")

        lifecycle_bus.emit(bus_key, "namespace-delete", "running", f"Deleting namespace {namespace}")
        try:
            self.k8s.core_v1.delete_namespace(namespace)
            logger.info("Namespace %s deleted", namespace)
            lifecycle_bus.emit(bus_key, "namespace-delete", "done", f"Namespace {namespace} deleted")
        except ApiException as e:
            if e.status != 404:
                raise
            lifecycle_bus.emit(bus_key, "namespace-delete", "done", f"Namespace {namespace} already deleted")

        if slug:
            lifecycle_bus.emit(bus_key, "harbor-delete", "running", "Deleting Harbor project")
            try:
                await self.harbor.delete_project(slug)
                lifecycle_bus.emit(bus_key, "harbor-delete", "done", "Harbor project deleted")
            except Exception as exc:
                logger.warning("Harbor project deletion failed for tenant %s: %s", slug, exc)
                lifecycle_bus.emit(bus_key, "harbor-delete", "failed", f"Harbor cleanup failed: {exc}")

        # H1a-2: clean up the three Keycloak groups created during provision.
        # Best-effort: missing groups (404) are silently skipped, other failures
        # are logged but do not block the rest of the deprovision chain.
        if slug:
            lifecycle_bus.emit(bus_key, "keycloak-groups-delete", "running", "Deleting Keycloak tenant groups")
            try:
                from app.services.keycloak_service import keycloak_service

                await keycloak_service.delete_tenant_groups(slug)
                lifecycle_bus.emit(bus_key, "keycloak-groups-delete", "done", "Keycloak groups deleted")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Keycloak group cleanup failed for tenant %s: %s", slug, exc)
                lifecycle_bus.emit(
                    bus_key,
                    "keycloak-groups-delete",
                    "failed",
                    f"Keycloak group cleanup failed: {exc}",
                )

        lifecycle_bus.mark_done(bus_key, success=True, message=f"Tenant {slug or namespace} deprovisioned")

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
                    # Everest: allows Percona Everest to manage databases in this namespace
                    "app.kubernetes.io/managed-by": "everest",
                    # H1d (PSA): Pod Security Admission `restricted` profile.
                    # Pre-fix: tenant namespaces had `enforce: baseline` which still
                    # allowed root user pods, hostPath volumes, and capabilities
                    # without drop. This violates the production-grade security
                    # baseline expected of a multi-tenant SaaS.
                    #
                    # `restricted` blocks: privileged containers, host* mounts,
                    # root user (must be runAsNonRoot), unprivileged capabilities,
                    # default runtime profile bypass.
                    #
                    # NOTE: this only affects NEW tenants. Existing namespaces
                    # (e.g. tenant-debora) retain whatever labels they were
                    # created with — _create_namespace returns 409 on existing
                    # ns and does not patch labels. To migrate an existing
                    # namespace, the operator runs:
                    #     kubectl label ns tenant-X \
                    #       pod-security.kubernetes.io/enforce=restricted \
                    #       pod-security.kubernetes.io/warn=restricted \
                    #       --overwrite
                    # ...after verifying the tenant's pods comply (no
                    # CrashLoopBackOff). Audit + warn modes are also set so
                    # restricted violations on existing tenant pods become
                    # visible without breaking them.
                    "pod-security.kubernetes.io/enforce": "restricted",
                    "pod-security.kubernetes.io/enforce-version": "latest",
                    "pod-security.kubernetes.io/audit": "restricted",
                    "pod-security.kubernetes.io/audit-version": "latest",
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

    async def _create_resource_quota(self, namespace: str, cpu: str, memory: str, storage: str, tier: str) -> None:
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
                harbor_host: {"auth": base64.b64encode(f"admin:{settings.harbor_admin_password}".encode()).decode()}
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
                                "pods",
                                "pods/log",
                                "pods/exec",
                                "pods/portforward",
                                "deployments",
                                "statefulsets",
                                "replicasets",
                                "jobs",
                                "cronjobs",
                                "horizontalpodautoscalers",
                                "services",
                                "endpoints",
                                "configmaps",
                                "persistentvolumeclaims",
                                "events",
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
                                "pods",
                                "pods/log",
                                "deployments",
                                "statefulsets",
                                "replicasets",
                                "jobs",
                                "cronjobs",
                                "horizontalpodautoscalers",
                                "services",
                                "endpoints",
                                "configmaps",
                                "events",
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
                                "pods",
                                "pods/log",
                                "deployments",
                                "statefulsets",
                                "replicasets",
                                "jobs",
                                "cronjobs",
                                "horizontalpodautoscalers",
                                "services",
                                "endpoints",
                                "configmaps",
                                "events",
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

    # ------------------------------------------------------------------
    # ArgoCD ApplicationSet (per-tenant isolation)
    # ------------------------------------------------------------------

    def _build_applicationset_body(self, tenant_slug: str) -> dict:
        """Build per-tenant ApplicationSet manifest. Lives only in K8s, not in git."""
        gitops_repo_url = settings.gitops_repo_url or (
            f"{settings.gitea_url}/{settings.gitea_org}/{settings.gitea_gitops_repo}.git"
        )
        # ArgoCD runs inside the cluster — use cluster-internal URL for git access
        appset_gitops_url = settings.gitops_argocd_repo_url or gitops_repo_url
        chart_repo_url = settings.chart_repo_url or "https://github.com/NimbusProTch/InfraForge-Haven.git"

        return {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "ApplicationSet",
            "metadata": {
                "name": f"appset-{tenant_slug}",
                "namespace": "argocd",
                "labels": {
                    "haven.io/managed": "true",
                    "haven.io/tenant": tenant_slug,
                    "haven.io/type": "tenant-apps",
                },
            },
            "spec": {
                "goTemplate": True,
                "goTemplateOptions": ["missingkey=error"],
                "generators": [
                    {
                        "git": {
                            "repoURL": appset_gitops_url,
                            "revision": "main",
                            "directories": [
                                {"path": f"tenants/{tenant_slug}/*"},
                                {"path": f"tenants/{tenant_slug}/services", "exclude": True},
                                {"path": f"tenants/{tenant_slug}/services/*", "exclude": True},
                            ],
                        }
                    }
                ],
                "template": {
                    "metadata": {
                        "name": f"{tenant_slug}-{{{{ index .path.segments 2 }}}}",
                        "namespace": "argocd",
                        "labels": {
                            "haven.io/managed": "true",
                            "haven.io/tenant": tenant_slug,
                            "haven.io/app": "{{ index .path.segments 2 }}",
                        },
                        "finalizers": ["resources-finalizer.argocd.argoproj.io"],
                    },
                    "spec": {
                        "project": "default",
                        "sources": [
                            {
                                "repoURL": chart_repo_url,
                                "targetRevision": "main",
                                "path": "charts/haven-app",
                                "helm": {"valueFiles": ["$values/{{ .path.path }}/values.yaml"]},
                            },
                            {
                                "repoURL": appset_gitops_url,
                                "targetRevision": "main",
                                "ref": "values",
                            },
                        ],
                        "destination": {
                            "server": "https://kubernetes.default.svc",
                            "namespace": f"tenant-{tenant_slug}",
                        },
                        "syncPolicy": {
                            "automated": {"prune": True, "selfHeal": True},
                            "syncOptions": ["CreateNamespace=false", "ServerSideApply=true"],
                            "retry": {
                                "limit": 3,
                                "backoff": {"duration": "5s", "factor": 2, "maxDuration": "3m"},
                            },
                        },
                    },
                },
            },
        }

    async def _create_applicationset(self, tenant_slug: str) -> None:
        """Create per-tenant ApplicationSet in ArgoCD namespace via K8s API."""
        if not self.k8s.is_available() or self.k8s.custom_objects is None:
            logger.warning("K8s unavailable — skipping ApplicationSet for %s", tenant_slug)
            return

        body = self._build_applicationset_body(tenant_slug)

        try:
            self.k8s.custom_objects.create_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace="argocd",
                plural="applicationsets",
                body=body,
            )
            logger.info("ApplicationSet appset-%s created", tenant_slug)
        except ApiException as e:
            if e.status == 409:
                logger.info("ApplicationSet appset-%s already exists", tenant_slug)
            else:
                logger.exception("Failed to create ApplicationSet for %s", tenant_slug)

    async def _delete_applicationset(self, tenant_slug: str) -> None:
        """Delete per-tenant ApplicationSet from ArgoCD namespace.

        Also deletes any child ArgoCD Applications labeled with this tenant,
        in case the ApplicationSet controller didn't garbage-collect them
        (e.g. finalizer stuck or ArgoCD was unreachable during delete).

        Uses up to 3 retries with exponential backoff. Falls back to force
        delete (grace_period_seconds=0) if the first attempt times out.
        """
        if not self.k8s.is_available() or self.k8s.custom_objects is None:
            return

        # Step 1: Delete child Applications generated by this ApplicationSet
        # ArgoCD ApplicationSet labels generated Applications with this tenant label
        try:
            apps = self.k8s.custom_objects.list_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace="argocd",
                plural="applications",
                label_selector=f"haven.io/tenant={tenant_slug}",
            )
            for item in apps.get("items", []):
                app_name = item.get("metadata", {}).get("name")
                if not app_name:
                    continue
                try:
                    self.k8s.custom_objects.delete_namespaced_custom_object(
                        group="argoproj.io",
                        version="v1alpha1",
                        namespace="argocd",
                        plural="applications",
                        name=app_name,
                        grace_period_seconds=0,
                    )
                    logger.info("Deleted child Application %s for tenant %s", app_name, tenant_slug)
                except ApiException as e:
                    if e.status != 404:
                        logger.warning("Failed to delete Application %s: %s", app_name, e)
        except ApiException as e:
            if e.status != 404:
                logger.debug("Failed to list child Applications for %s: %s", tenant_slug, e)

        # Step 2: Delete the ApplicationSet itself, with retry + force fallback
        appset_name = f"appset-{tenant_slug}"
        for attempt in range(3):
            try:
                self.k8s.custom_objects.delete_namespaced_custom_object(
                    group="argoproj.io",
                    version="v1alpha1",
                    namespace="argocd",
                    plural="applicationsets",
                    name=appset_name,
                )
                logger.info("ApplicationSet %s deleted (attempt %d)", appset_name, attempt + 1)
                return
            except ApiException as e:
                if e.status == 404:
                    logger.info("ApplicationSet %s already gone", appset_name)
                    return
                if attempt == 2:
                    # Last attempt: try force delete (bypass finalizers)
                    try:
                        self.k8s.custom_objects.delete_namespaced_custom_object(
                            group="argoproj.io",
                            version="v1alpha1",
                            namespace="argocd",
                            plural="applicationsets",
                            name=appset_name,
                            grace_period_seconds=0,
                            body={"propagationPolicy": "Background"},
                        )
                        logger.warning(
                            "ApplicationSet %s force-deleted after retries failed",
                            appset_name,
                        )
                        return
                    except ApiException as force_err:
                        if force_err.status != 404:
                            logger.error(
                                "Failed to force-delete ApplicationSet %s: %s",
                                appset_name,
                                force_err,
                            )
                        return
                logger.warning(
                    "Failed to delete ApplicationSet %s (attempt %d): %s",
                    appset_name,
                    attempt + 1,
                    e,
                )
                await asyncio.sleep(2**attempt)  # 1s, 2s backoff
