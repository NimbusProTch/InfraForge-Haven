"""Managed service provisioning: PostgreSQL, MySQL, MongoDB via Everest; Redis, RabbitMQ via K8s CRDs."""

import logging

from kubernetes.client.exceptions import ApiException

from app.config import settings
from app.k8s.client import K8sClient
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType
from app.services.everest_client import EverestClient, everest_client

logger = logging.getLogger(__name__)

# Engine types that should be routed through Everest when available
_EVEREST_ENGINES = {ServiceType.POSTGRES, ServiceType.MYSQL, ServiceType.MONGODB}

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
    ServiceType.POSTGRES: lambda name: f"{name}-app",  # CNPG/Percona app user secret
    ServiceType.MYSQL: lambda name: f"{name}-pxc-secrets",  # Percona XtraDB secret
    ServiceType.MONGODB: lambda name: f"{name}-psmdb-secrets",  # Percona MongoDB secret
    ServiceType.REDIS: lambda name: f"{name}-redis",  # OpsTree Redis secret
    ServiceType.RABBITMQ: lambda name: f"{name}-default-user",  # RabbitMQ Operator default user
}

# Everest-managed DBs use a different secret naming convention
_EVEREST_SECRET_NAME = lambda name: f"everest-secrets-{name}"  # noqa: E731
# Everest creates secrets in its own namespace, not the tenant namespace
EVEREST_NAMESPACE = getattr(settings, "everest_namespace", "") or "everest"

_CONNECTION_HINT_MAP = {
    ServiceType.POSTGRES: lambda name, ns: f"postgresql://{name}-app@{name}-rw.{ns}.svc:5432/{name.replace('-', '_')}",
    ServiceType.MYSQL: lambda name, ns: f"mysql://{name}-pxc@{name}-haproxy.{ns}.svc:3306/{name.replace('-', '_')}",
    ServiceType.MONGODB: lambda name, ns: f"mongodb://{name}-rs0@{name}-mongos.{ns}.svc:27017/{name.replace('-', '_')}",
    ServiceType.REDIS: lambda name, ns: f"redis://{name}-redis.{ns}.svc:6379",
    ServiceType.RABBITMQ: lambda name, ns: f"amqp://{name}-default-user@{name}.{ns}.svc:5672",
}


def _mysql_body(name: str, namespace: str, tier: ServiceTier) -> dict:
    """Build a Percona XtraDB Cluster manifest."""
    instances = 1 if tier == ServiceTier.DEV else 3
    storage = "5Gi" if tier == ServiceTier.DEV else "20Gi"
    return {
        "apiVersion": "pxc.percona.com/v1",
        "kind": "PerconaXtraDBCluster",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "crVersion": "1.15.0",
            "allowUnsafeConfigurations": tier == ServiceTier.DEV,
            "pxc": {
                "size": instances,
                "image": "percona/percona-xtradb-cluster:8.0",
                "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"memory": "1Gi"}},
                "volumeSpec": {
                    "persistentVolumeClaim": {
                        "storageClassName": "longhorn",
                        "resources": {"requests": {"storage": storage}},
                    }
                },
                "affinity": {"advanced": {"tolerations": [{"operator": "Exists"}]}},
            },
            "haproxy": {
                "enabled": True,
                "size": 1 if tier == ServiceTier.DEV else 2,
                "image": "percona/haproxy:2.8.5",
                "tolerations": [{"operator": "Exists"}],
            },
        },
    }


def _mongodb_body(name: str, namespace: str, tier: ServiceTier) -> dict:
    """Build a Percona Server for MongoDB manifest."""
    instances = 1 if tier == ServiceTier.DEV else 3
    storage = "5Gi" if tier == ServiceTier.DEV else "20Gi"
    return {
        "apiVersion": "psmdb.percona.com/v1",
        "kind": "PerconaServerMongoDB",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "crVersion": "1.17.0",
            "image": "percona/percona-server-mongodb:7.0",
            "allowUnsafeConfigurations": tier == ServiceTier.DEV,
            "replsets": [
                {
                    "name": "rs0",
                    "size": instances,
                    "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"memory": "1Gi"}},
                    "volumeSpec": {
                        "persistentVolumeClaim": {
                            "storageClassName": "longhorn",
                            "resources": {"requests": {"storage": storage}},
                        }
                    },
                    "affinity": {"advanced": {"tolerations": [{"operator": "Exists"}]}},
                }
            ],
            "sharding": {"enabled": False},
        },
    }


_CRD_CONFIG = {
    ServiceType.POSTGRES: {
        "group": "postgresql.cnpg.io",
        "version": "v1",
        "plural": "clusters",
        "body_fn": _cnpg_cluster_body,
    },
    ServiceType.MYSQL: {
        "group": "pxc.percona.com",
        "version": "v1",
        "plural": "perconaxtradbclusters",
        "body_fn": _mysql_body,
    },
    ServiceType.MONGODB: {
        "group": "psmdb.percona.com",
        "version": "v1",
        "plural": "perconaservermongodbs",
        "body_fn": _mongodb_body,
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
    """Creates and deletes managed service CRDs or Everest databases in tenant namespaces.

    PostgreSQL, MySQL, and MongoDB are routed through Percona Everest API when available.
    Redis and RabbitMQ always use direct K8s CRDs (OpsTree / RabbitMQ Operator).
    Falls back to direct CRDs if Everest is not configured or unreachable.
    """

    def __init__(self, k8s: K8sClient, everest: EverestClient | None = None) -> None:
        self.k8s = k8s
        self.everest = everest or everest_client

    def _use_everest(self, service_type: ServiceType) -> bool:
        """Return True if this service type should be provisioned via Everest."""
        return service_type in _EVEREST_ENGINES and self.everest.is_configured()

    # ------------------------------------------------------------------
    # Everest-based provisioning (PostgreSQL, MySQL, MongoDB)
    # ------------------------------------------------------------------

    async def _everest_provision(self, service: ManagedService, tenant_namespace: str) -> None:
        """Provision a database via Percona Everest REST API."""
        engine_map = {ServiceType.POSTGRES: "postgres", ServiceType.MYSQL: "mysql", ServiceType.MONGODB: "mongodb"}
        engine_type = engine_map[service.service_type]
        tier = "dev" if service.tier == ServiceTier.DEV else "prod"

        try:
            result = await self.everest.create_database(
                name=service.name,
                engine_type=engine_type,
                tier=tier,
            )
            logger.info("Everest DB created: %s (%s)", service.name, engine_type)
        except Exception:
            logger.exception("Everest provision failed for %s — falling back to CRD", service.name)
            await self._crd_provision(service, tenant_namespace)
            return

        # Everest creates secrets in its own namespace with a different naming convention
        service.service_namespace = EVEREST_NAMESPACE
        service.secret_name = _EVEREST_SECRET_NAME(service.name)
        service.connection_hint = _CONNECTION_HINT_MAP[service.service_type](
            service.name, EVEREST_NAMESPACE
        )
        service.status = ServiceStatus.PROVISIONING

    async def _everest_update(
        self,
        service: ManagedService,
        *,
        replicas: int | None = None,
        storage: str | None = None,
        cpu: str | None = None,
        memory: str | None = None,
    ) -> None:
        """Update a database via Everest API."""
        try:
            await self.everest.update_database(
                service.name,
                replicas=replicas,
                storage=storage,
                cpu=cpu,
                memory=memory,
            )
            logger.info("Everest DB updated: %s", service.name)
        except Exception:
            logger.exception("Everest update failed for %s", service.name)

    async def _everest_sync_status(self, service: ManagedService) -> None:
        """Sync status from Everest API."""
        try:
            status = await self.everest.get_database_status(service.name)
        except Exception:
            logger.exception("Everest status check failed for %s", service.name)
            return

        if status == "ready":
            service.status = ServiceStatus.READY
        elif status in ("error", "failed", "not_found"):
            service.status = ServiceStatus.FAILED

    async def _everest_deprovision(self, service: ManagedService) -> None:
        """Delete a database via Everest API."""
        try:
            await self.everest.delete_database(service.name)
            logger.info("Everest DB deleted: %s", service.name)
        except Exception:
            logger.exception("Everest deprovision failed for %s", service.name)

    # ------------------------------------------------------------------
    # CRD-based provisioning (Redis, RabbitMQ, and fallback)
    # ------------------------------------------------------------------

    async def _crd_provision(self, service: ManagedService, tenant_namespace: str) -> None:
        """Provision a service via direct K8s CRD."""
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
        service.connection_hint = _CONNECTION_HINT_MAP[service.service_type](service.name, tenant_namespace)
        service.status = ServiceStatus.PROVISIONING

    async def _crd_sync_status(self, service: ManagedService) -> None:
        """Sync status from K8s CRD."""
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
        elif svc_type == ServiceType.MYSQL or svc_type == ServiceType.MONGODB:
            state = k8s_status.get("state", "")
            if state == "ready":
                service.status = ServiceStatus.READY
            elif state in ("error", "failed"):
                service.status = ServiceStatus.FAILED
        elif svc_type == ServiceType.RABBITMQ:
            conditions = k8s_status.get("conditions", [])
            for cond in conditions:
                if cond.get("type") == "AllReplicasReady" and cond.get("status") == "True":
                    service.status = ServiceStatus.READY
                    break

    async def _crd_deprovision(self, service: ManagedService) -> None:
        """Delete a service CRD."""
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

    # ------------------------------------------------------------------
    # Public API — routes to Everest or CRD based on service type
    # ------------------------------------------------------------------

    async def sync_status(self, service: ManagedService) -> None:
        """Check status and update service.status accordingly."""
        if self._use_everest(service.service_type):
            await self._everest_sync_status(service)
        else:
            await self._crd_sync_status(service)

    async def provision(self, service: ManagedService, tenant_namespace: str) -> None:
        """Create the database/service and populate secret_name + connection_hint."""
        if self._use_everest(service.service_type):
            await self._everest_provision(service, tenant_namespace)
        else:
            await self._crd_provision(service, tenant_namespace)
        logger.info(
            "Service %s (%s) provisioned in %s via %s",
            service.name,
            service.service_type,
            tenant_namespace,
            "Everest" if self._use_everest(service.service_type) else "CRD",
        )

    async def update(
        self,
        service: ManagedService,
        *,
        replicas: int | None = None,
        storage: str | None = None,
        cpu: str | None = None,
        memory: str | None = None,
    ) -> None:
        """Update the database/service resources."""
        if self._use_everest(service.service_type):
            await self._everest_update(
                service, replicas=replicas, storage=storage, cpu=cpu, memory=memory
            )
        else:
            logger.warning("CRD-based update not implemented for %s", service.name)

    async def deprovision(self, service: ManagedService) -> None:
        """Delete the database/service."""
        if self._use_everest(service.service_type):
            await self._everest_deprovision(service)
        else:
            await self._crd_deprovision(service)
