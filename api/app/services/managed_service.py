"""Managed service provisioning: PostgreSQL, MySQL, MongoDB via Everest; Redis, RabbitMQ via K8s CRDs."""

import base64
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


def _cnpg_cluster_body(
    name: str, namespace: str, tier: ServiceTier, *, db_name: str | None = None, db_user: str | None = None
) -> dict:
    """Build a CNPG Cluster manifest for a tenant PostgreSQL instance."""
    instances = 1 if tier == ServiceTier.DEV else 3
    storage = "5Gi" if tier == ServiceTier.DEV else "20Gi"
    database = db_name or name.replace("-", "_")
    owner = db_user or (database + "_user")
    return {
        "apiVersion": "postgresql.cnpg.io/v1",
        "kind": "Cluster",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "instances": instances,
            "storage": {"storageClass": "longhorn", "size": storage},
            "bootstrap": {
                "initdb": {
                    "database": database,
                    "owner": owner,
                }
            },
            "affinity": {"tolerations": [{"operator": "Exists"}]},
        },
    }


def _redis_body(name: str, namespace: str, tier: ServiceTier) -> dict:
    """Build a Redis CRD manifest (OpsTree Redis Operator)."""
    spec: dict = {
        "kubernetesConfig": {
            "image": "quay.io/opstree/redis:v7.0.15",
            "imagePullPolicy": "IfNotPresent",
        },
        "tolerations": [{"operator": "Exists"}],
    }
    if tier == ServiceTier.PROD:
        # Prod: persistent storage with init container for volume ownership
        spec["storage"] = {
            "keepAfterDelete": True,
            "volumeClaimTemplate": {
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "storageClassName": "longhorn",
                    "resources": {"requests": {"storage": "5Gi"}},
                }
            },
        }
    # Dev: no persistent storage (ephemeral, avoids Longhorn permission issues)
    return {
        "apiVersion": "redis.redis.opstreelabs.in/v1beta2",
        "kind": "Redis",
        "metadata": {"name": name, "namespace": namespace},
        "spec": spec,
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
    ServiceType.REDIS: lambda name, ns: f"redis://{name}.{ns}.svc:6379",
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

    def _sync_from_pod(self, service: ManagedService, pod_name: str) -> None:
        """Fallback health check: inspect pod status when CRD status is empty."""
        if not self.k8s.core_v1:
            return
        try:
            pod = self.k8s.core_v1.read_namespaced_pod(
                name=pod_name, namespace=service.service_namespace
            )
        except ApiException as e:
            if e.status == 404 and service.status == ServiceStatus.READY:
                service.status = ServiceStatus.DEGRADED
                service.error_message = "Pod not found"
            return

        phase = pod.status.phase if pod.status else None
        containers = pod.status.container_statuses or [] if pod.status else []

        if phase == "Running" and containers and all(c.ready for c in containers):
            service.status = ServiceStatus.READY
            service.error_message = None
            return

        # Detect specific failure reasons for user-friendly messages
        error_msg = None
        for c in containers:
            if c.last_state and c.last_state.terminated:
                reason = c.last_state.terminated.reason or ""
                if reason == "OOMKilled":
                    error_msg = "Out of memory — consider increasing memory limit"
                elif reason:
                    error_msg = f"Container terminated: {reason}"
            if c.state and c.state.waiting:
                reason = c.state.waiting.reason or ""
                if reason == "CrashLoopBackOff":
                    error_msg = "Service crashing — check logs"
                elif reason == "ImagePullBackOff":
                    error_msg = "Failed to pull container image"

        if error_msg:
            service.error_message = error_msg
            if service.status == ServiceStatus.READY:
                service.status = ServiceStatus.DEGRADED
            elif service.status == ServiceStatus.PROVISIONING:
                service.status = ServiceStatus.FAILED

    # ------------------------------------------------------------------
    # Everest-based provisioning (PostgreSQL, MySQL, MongoDB)
    # ------------------------------------------------------------------

    async def _everest_provision(self, service: ManagedService, tenant_namespace: str, tenant_slug: str) -> None:
        """Provision a database via Percona Everest REST API."""
        engine_map = {ServiceType.POSTGRES: "postgres", ServiceType.MYSQL: "mysql", ServiceType.MONGODB: "mongodb"}
        engine_type = engine_map[service.service_type]
        tier = "dev" if service.tier == ServiceTier.DEV else "prod"

        # Prefix DB name with tenant slug for namespace isolation
        everest_name = f"{tenant_slug}-{service.name}"

        try:
            await self.everest.create_database(
                name=everest_name,
                engine_type=engine_type,
                tier=tier,
            )
            logger.info("Everest DB created: %s → %s (%s)", service.name, everest_name, engine_type)
        except Exception:
            logger.exception("Everest provision failed for %s — falling back to CRD", service.name)
            await self._crd_provision(service, tenant_namespace)
            return

        # Store the Everest-side name for all future API calls
        service.everest_name = everest_name
        service.service_namespace = EVEREST_NAMESPACE
        service.secret_name = _EVEREST_SECRET_NAME(everest_name)
        service.connection_hint = _CONNECTION_HINT_MAP[service.service_type](
            everest_name, EVEREST_NAMESPACE
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
        ev_name = service.everest_name or service.name
        try:
            await self.everest.update_database(
                ev_name,
                replicas=replicas,
                storage=storage,
                cpu=cpu,
                memory=memory,
            )
            service.status = ServiceStatus.UPDATING
            service.error_message = None
            logger.info("Everest DB updated: %s", ev_name)
        except Exception:
            logger.exception("Everest update failed for %s", ev_name)
            service.error_message = "Update request failed"

    async def _everest_sync_status(self, service: ManagedService) -> None:
        """Sync status from Everest API."""
        ev_name = service.everest_name or service.name
        try:
            status = await self.everest.get_database_status(ev_name)
        except Exception:
            logger.exception("Everest status check failed for %s", ev_name)
            return

        if status == "ready":
            service.status = ServiceStatus.READY
            service.error_message = None
        elif status in ("error", "failed", "not_found"):
            service.status = ServiceStatus.FAILED

    async def _everest_sync_details(self, service: ManagedService) -> dict | None:
        """Sync status and return runtime details for UI enrichment."""
        ev_name = service.everest_name or service.name
        try:
            details = await self.everest.get_database_details(ev_name)
        except Exception:
            logger.exception("Everest details fetch failed for %s", ev_name)
            return None

        ev_status = details.get("status", "unknown")
        if ev_status == "ready":
            service.status = ServiceStatus.READY
            service.error_message = None
        elif ev_status in ("error", "failed", "not_found"):
            service.status = ServiceStatus.FAILED
            service.error_message = details.get("error_message")

        return details

    async def _everest_deprovision(self, service: ManagedService) -> None:
        """Delete a database via Everest API."""
        ev_name = service.everest_name or service.name
        try:
            await self.everest.delete_database(ev_name)
            logger.info("Everest DB deleted: %s", ev_name)
        except Exception:
            logger.exception("Everest deprovision failed for %s", ev_name)

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
        # Pass custom db_name/db_user to CNPG builder
        if service.service_type == ServiceType.POSTGRES:
            body = cfg["body_fn"](service.name, tenant_namespace, service.tier, db_name=service.db_name, db_user=service.db_user)
        else:
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
        # Override connection_hint with custom db_name for CNPG
        if service.service_type == ServiceType.POSTGRES and service.db_name:
            db_user = service.db_user or (service.db_name + "_user")
            service.connection_hint = (
                f"postgresql://{db_user}@{service.name}-rw.{tenant_namespace}.svc:5432/{service.db_name}"
            )
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
                service.error_message = None
            else:
                # OpsTree Redis operator may not populate CRD status — check pod
                self._sync_from_pod(service, f"{service.name}-0")
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

    async def sync_details(self, service: ManagedService, tenant_namespace: str = "") -> dict | None:
        """Sync status and return runtime details dict for UI enrichment.

        When an Everest DB transitions to READY for the first time, provisions
        custom database/user and creates a credentials secret in the tenant namespace.
        """
        if self._use_everest(service.service_type):
            details = await self._everest_sync_details(service)

            # Post-provision: create custom user/db + tenant secret when first READY
            if (
                service.status == ServiceStatus.READY
                and not service.credentials_provisioned
                and tenant_namespace
            ):
                await self._provision_custom_credentials(service, tenant_namespace)

            return details

        # CRD path: sync status only, create standardized secret when ready
        await self._crd_sync_status(service)
        if (
            service.status == ServiceStatus.READY
            and not service.credentials_provisioned
            and tenant_namespace
        ):
            await self._create_crd_tenant_secret(service, tenant_namespace)

        return None

    async def _provision_custom_credentials(self, service: ManagedService, tenant_namespace: str) -> None:
        """Create custom DB user/database and a secret in the tenant namespace."""
        from app.services.db_provisioner import (
            create_custom_database,
            create_tenant_secret,
            tenant_secret_name,
        )

        if not service.secret_name:
            return

        try:
            db_name = service.db_name or service.name.replace("-", "_")
            db_user = service.db_user or db_name

            credentials = await create_custom_database(
                k8s=self.k8s,
                everest_secret_name=service.secret_name,
                db_name=db_name,
                db_user=db_user,
            )

            target_secret = tenant_secret_name(service.name)
            await create_tenant_secret(self.k8s, tenant_namespace, target_secret, credentials)

            # Update service to point to the tenant namespace secret
            service.secret_name = target_secret
            service.service_namespace = tenant_namespace
            service.db_name = db_name
            service.db_user = db_user
            db_url = credentials["DATABASE_URL"]
            service.connection_hint = db_url.split("@")[0].rsplit(":", 1)[0] + ":***@" + db_url.split("@")[1]
            service.credentials_provisioned = True

            logger.info("Custom credentials provisioned for %s → %s/%s", service.name, tenant_namespace, target_secret)
        except Exception:
            logger.exception("Failed to provision custom credentials for %s", service.name)

    async def _create_crd_tenant_secret(self, service: ManagedService, tenant_namespace: str) -> None:
        """Create a standardized secret in tenant namespace for CRD-based services."""
        from app.services.db_provisioner import create_tenant_secret, tenant_secret_name

        if not service.secret_name or not service.service_namespace:
            return

        try:
            # Read the existing CRD secret
            if not self.k8s.is_available() or self.k8s.core_v1 is None:
                return

            source_secret = self.k8s.core_v1.read_namespaced_secret(
                name=service.secret_name, namespace=service.service_namespace
            )
            creds: dict[str, str] = {}
            for key, val in (source_secret.data or {}).items():
                creds[key] = base64.b64decode(val).decode()

            # Add standardized URL
            if service.service_type == ServiceType.REDIS:
                host = f"{service.name}.{tenant_namespace}.svc"
                creds["REDIS_URL"] = f"redis://{host}:6379"
            elif service.service_type == ServiceType.RABBITMQ:
                user = creds.get("username", "guest")
                password = creds.get("password", "guest")
                host = f"{service.name}.{tenant_namespace}.svc"
                creds["RABBITMQ_URL"] = f"amqp://{user}:{password}@{host}:5672"

            target_secret = tenant_secret_name(service.name)
            await create_tenant_secret(self.k8s, tenant_namespace, target_secret, creds)

            service.secret_name = target_secret
            service.credentials_provisioned = True
            logger.info("CRD tenant secret created for %s → %s/%s", service.name, tenant_namespace, target_secret)
        except Exception:
            logger.exception("Failed to create CRD tenant secret for %s", service.name)

    async def provision(self, service: ManagedService, tenant_namespace: str, tenant_slug: str = "") -> None:
        """Create the database/service and populate secret_name + connection_hint."""
        if self._use_everest(service.service_type):
            slug = tenant_slug or tenant_namespace.removeprefix("tenant-")
            await self._everest_provision(service, tenant_namespace, slug)
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
