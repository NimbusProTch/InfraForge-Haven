"""Managed service provisioning: PostgreSQL (CNPG), Redis, RabbitMQ CRDs."""

import logging

from kubernetes.client.exceptions import ApiException

from app.k8s.client import K8sClient
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CRD body builders
# ---------------------------------------------------------------------------


def _cnpg_cluster_body(name: str, namespace: str, tier: ServiceTier) -> dict:
    """Build a CNPG Cluster manifest for a tenant PostgreSQL instance."""
    instances = 1 if tier == ServiceTier.DEV else 3
    storage = "5Gi" if tier == ServiceTier.DEV else "20Gi"
    return {
        "apiVersion": "postgresql.cnpg.io/v1",
        "kind": "Cluster",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "instances": instances,
            "storage": {"storageClass": "longhorn", "size": storage},
            "bootstrap": {
                "initdb": {
                    "database": name.replace("-", "_"),
                    "owner": name.replace("-", "_") + "_user",
                }
            },
            "affinity": {"tolerations": [{"operator": "Exists"}]},
        },
    }


def _redis_body(name: str, namespace: str, tier: ServiceTier) -> dict:
    """Build a Redis CRD manifest (OpsTree Redis Operator)."""
    size = "1Gi" if tier == ServiceTier.DEV else "5Gi"
    return {
        "apiVersion": "redis.redis.opstreelabs.in/v1beta2",
        "kind": "Redis",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "kubernetesConfig": {
                "image": "quay.io/opstree/redis:v7.0.15",
                "imagePullPolicy": "IfNotPresent",
            },
            "storage": {
                "volumeClaimTemplate": {
                    "spec": {
                        "accessModes": ["ReadWriteOnce"],
                        "storageClassName": "longhorn",
                        "resources": {"requests": {"storage": size}},
                    }
                }
            },
            "tolerations": [{"operator": "Exists"}],
        },
    }


def _rabbitmq_body(name: str, namespace: str, tier: ServiceTier) -> dict:
    """Build a RabbitmqCluster manifest (RabbitMQ Cluster Operator)."""
    replicas = 1 if tier == ServiceTier.DEV else 3
    storage = "5Gi" if tier == ServiceTier.DEV else "10Gi"
    return {
        "apiVersion": "rabbitmq.com/v1beta1",
        "kind": "RabbitmqCluster",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "replicas": replicas,
            "persistence": {
                "storageClassName": "longhorn",
                "storage": storage,
            },
            "tolerations": [{"operator": "Exists"}],
        },
    }


# ---------------------------------------------------------------------------
# Secret name helpers (each operator creates a predictable secret)
# ---------------------------------------------------------------------------

_SECRET_NAME_MAP = {
    ServiceType.POSTGRES: lambda name: f"{name}-app",     # CNPG app user secret
    ServiceType.REDIS: lambda name: f"{name}-redis",      # OpsTree Redis secret
    ServiceType.RABBITMQ: lambda name: f"{name}-default-user",  # RabbitMQ Operator default user
}

_CONNECTION_HINT_MAP = {
    ServiceType.POSTGRES: lambda name, ns: f"postgresql://{name}-app@{name}-rw.{ns}.svc:5432/{name.replace('-', '_')}",
    ServiceType.REDIS: lambda name, ns: f"redis://{name}-redis.{ns}.svc:6379",
    ServiceType.RABBITMQ: lambda name, ns: f"amqp://{name}-default-user@{name}.{ns}.svc:5672",
}

_CRD_CONFIG = {
    ServiceType.POSTGRES: {
        "group": "postgresql.cnpg.io",
        "version": "v1",
        "plural": "clusters",
        "body_fn": _cnpg_cluster_body,
    },
    ServiceType.REDIS: {
        "group": "redis.redis.opstreelabs.in",
        "version": "v1beta2",
        "plural": "redis",
        "body_fn": _redis_body,
    },
    ServiceType.RABBITMQ: {
        "group": "rabbitmq.com",
        "version": "v1beta1",
        "plural": "rabbitmqclusters",
        "body_fn": _rabbitmq_body,
    },
}


class ManagedServiceProvisioner:
    """Creates and deletes managed service CRDs in tenant namespaces."""

    def __init__(self, k8s: K8sClient) -> None:
        self.k8s = k8s

    async def sync_status(self, service: ManagedService) -> None:
        """Check the K8s CRD status and update service.status accordingly."""
        if not self.k8s.is_available() or self.k8s.custom_objects is None:
            return
        if not service.service_namespace:
            return

        cfg = _CRD_CONFIG[service.service_type]
        try:
            obj = self.k8s.custom_objects.get_namespaced_custom_object(
                group=cfg["group"],
                version=cfg["version"],
                namespace=service.service_namespace,
                plural=cfg["plural"],
                name=service.name,
            )
        except ApiException as e:
            if e.status == 404:
                service.status = ServiceStatus.FAILED
            return

        # Determine ready state based on operator-specific status fields
        svc_type = service.service_type
        k8s_status = obj.get("status", {})
        if svc_type == ServiceType.POSTGRES:
            phase = k8s_status.get("phase", "")
            ready_instances = k8s_status.get("readyInstances", 0)
            instances = obj.get("spec", {}).get("instances", 1)
            if phase == "Cluster in healthy state" or (ready_instances and ready_instances >= instances):
                service.status = ServiceStatus.READY
            elif phase in ("Failed", "Error"):
                service.status = ServiceStatus.FAILED
        elif svc_type == ServiceType.REDIS:
            ready = k8s_status.get("readyReplicas", 0)
            if ready and ready > 0:
                service.status = ServiceStatus.READY
        elif svc_type == ServiceType.RABBITMQ:
            ready_replicas = k8s_status.get("observedGeneration")
            conditions = k8s_status.get("conditions", [])
            for cond in conditions:
                if cond.get("type") == "AllReplicasReady" and cond.get("status") == "True":
                    service.status = ServiceStatus.READY
                    break

    async def provision(self, service: ManagedService, tenant_namespace: str) -> None:
        """Create the operator CRD and populate secret_name + connection_hint."""
        if not self.k8s.is_available() or self.k8s.custom_objects is None:
            logger.warning("K8s unavailable — skipping provision for service %s", service.name)
            service.status = ServiceStatus.FAILED
            return

        cfg = _CRD_CONFIG[service.service_type]
        body = cfg["body_fn"](service.name, tenant_namespace, service.tier)

        try:
            self.k8s.custom_objects.create_namespaced_custom_object(
                group=cfg["group"],
                version=cfg["version"],
                namespace=tenant_namespace,
                plural=cfg["plural"],
                body=body,
            )
        except ApiException as e:
            if e.status == 409:
                logger.info("CRD %s/%s already exists — skipping", tenant_namespace, service.name)
            else:
                logger.exception("Failed to create CRD for service %s", service.name)
                service.status = ServiceStatus.FAILED
                return

        service.secret_name = _SECRET_NAME_MAP[service.service_type](service.name)
        service.service_namespace = tenant_namespace
        service.connection_hint = _CONNECTION_HINT_MAP[service.service_type](
            service.name, tenant_namespace
        )
        service.status = ServiceStatus.PROVISIONING  # operator will flip to READY eventually
        logger.info(
            "Service %s (%s) CRD created in %s",
            service.name,
            service.service_type,
            tenant_namespace,
        )

    async def deprovision(self, service: ManagedService) -> None:
        """Delete the operator CRD."""
        if not self.k8s.is_available() or self.k8s.custom_objects is None:
            return
        if not service.service_namespace:
            return

        cfg = _CRD_CONFIG[service.service_type]
        try:
            self.k8s.custom_objects.delete_namespaced_custom_object(
                group=cfg["group"],
                version=cfg["version"],
                namespace=service.service_namespace,
                plural=cfg["plural"],
                name=service.name,
            )
            logger.info("Service CRD %s/%s deleted", service.service_namespace, service.name)
        except ApiException as e:
            if e.status != 404:
                raise
