"""Unit tests for ManagedServiceProvisioner and CRD body builders."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kubernetes.client.exceptions import ApiException

from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType
from app.services.everest_client import EverestClient
from app.services.managed_service import (
    _CONNECTION_HINT_MAP,
    _EVEREST_ENGINES,
    _SECRET_NAME_MAP,
    ManagedServiceProvisioner,
    _cnpg_cluster_body,
    _mongodb_body,
    _mysql_body,
    _rabbitmq_body,
    _redis_body,
)

# ---------------------------------------------------------------------------
# CRD body builders
# ---------------------------------------------------------------------------


class TestCnpgBody:
    def test_dev_tier(self):
        body = _cnpg_cluster_body("my-pg", "tenant-acme", ServiceTier.DEV)
        assert body["kind"] == "Cluster"
        assert body["apiVersion"] == "postgresql.cnpg.io/v1"
        assert body["spec"]["instances"] == 1
        assert body["spec"]["storage"]["size"] == "5Gi"
        assert body["metadata"]["namespace"] == "tenant-acme"

    def test_prod_tier(self):
        body = _cnpg_cluster_body("my-pg", "tenant-acme", ServiceTier.PROD)
        assert body["spec"]["instances"] == 3
        assert body["spec"]["storage"]["size"] == "20Gi"

    def test_database_name_uses_underscores(self):
        body = _cnpg_cluster_body("my-pg", "tenant-acme", ServiceTier.DEV)
        assert body["spec"]["bootstrap"]["initdb"]["database"] == "my_pg"

    def test_tolerations_present(self):
        body = _cnpg_cluster_body("my-pg", "tenant-acme", ServiceTier.DEV)
        assert body["spec"]["affinity"]["tolerations"] == [{"operator": "Exists"}]


class TestMysqlBody:
    def test_dev_tier(self):
        body = _mysql_body("my-mysql", "tenant-acme", ServiceTier.DEV)
        assert body["kind"] == "PerconaXtraDBCluster"
        assert body["apiVersion"] == "pxc.percona.com/v1"
        assert body["spec"]["pxc"]["size"] == 1
        assert body["spec"]["haproxy"]["size"] == 1
        assert body["spec"]["allowUnsafeConfigurations"] is True

    def test_prod_tier(self):
        body = _mysql_body("my-mysql", "tenant-acme", ServiceTier.PROD)
        assert body["spec"]["pxc"]["size"] == 3
        assert body["spec"]["haproxy"]["size"] == 2
        assert body["spec"]["allowUnsafeConfigurations"] is False

    def test_storage_sizes(self):
        dev = _mysql_body("x", "ns", ServiceTier.DEV)
        prod = _mysql_body("x", "ns", ServiceTier.PROD)
        assert dev["spec"]["pxc"]["volumeSpec"]["persistentVolumeClaim"]["resources"]["requests"]["storage"] == "5Gi"
        assert prod["spec"]["pxc"]["volumeSpec"]["persistentVolumeClaim"]["resources"]["requests"]["storage"] == "20Gi"


class TestMongodbBody:
    def test_dev_tier(self):
        body = _mongodb_body("my-mongo", "tenant-acme", ServiceTier.DEV)
        assert body["kind"] == "PerconaServerMongoDB"
        assert body["apiVersion"] == "psmdb.percona.com/v1"
        assert body["spec"]["replsets"][0]["size"] == 1
        assert body["spec"]["allowUnsafeConfigurations"] is True

    def test_prod_tier(self):
        body = _mongodb_body("my-mongo", "tenant-acme", ServiceTier.PROD)
        assert body["spec"]["replsets"][0]["size"] == 3
        assert body["spec"]["allowUnsafeConfigurations"] is False

    def test_sharding_disabled(self):
        body = _mongodb_body("my-mongo", "tenant-acme", ServiceTier.DEV)
        assert body["spec"]["sharding"]["enabled"] is False

    def test_replset_name_is_rs0(self):
        body = _mongodb_body("my-mongo", "tenant-acme", ServiceTier.DEV)
        assert body["spec"]["replsets"][0]["name"] == "rs0"


class TestRedisBody:
    def test_dev_tier(self):
        body = _redis_body("my-redis", "tenant-acme", ServiceTier.DEV)
        assert body["kind"] == "Redis"
        assert body["apiVersion"] == "redis.redis.opstreelabs.in/v1beta2"
        assert "storage" not in body["spec"]  # Dev: ephemeral, no persistent storage

    def test_prod_tier(self):
        body = _redis_body("my-redis", "tenant-acme", ServiceTier.PROD)
        storage_size = body["spec"]["storage"]["volumeClaimTemplate"]["spec"]["resources"]["requests"]["storage"]
        assert storage_size == "5Gi"

    def test_tolerations_present(self):
        body = _redis_body("my-redis", "tenant-acme", ServiceTier.DEV)
        assert body["spec"]["tolerations"] == [{"operator": "Exists"}]


class TestRabbitmqBody:
    def test_dev_tier(self):
        body = _rabbitmq_body("my-rmq", "tenant-acme", ServiceTier.DEV)
        assert body["kind"] == "RabbitmqCluster"
        assert body["apiVersion"] == "rabbitmq.com/v1beta1"
        assert body["spec"]["replicas"] == 1
        assert body["spec"]["persistence"]["storage"] == "5Gi"

    def test_prod_tier(self):
        body = _rabbitmq_body("my-rmq", "tenant-acme", ServiceTier.PROD)
        assert body["spec"]["replicas"] == 3
        assert body["spec"]["persistence"]["storage"] == "10Gi"

    def test_storage_class_is_longhorn(self):
        body = _rabbitmq_body("my-rmq", "tenant-acme", ServiceTier.DEV)
        assert body["spec"]["persistence"]["storageClassName"] == "longhorn"


# ---------------------------------------------------------------------------
# Secret name and connection hint maps
# ---------------------------------------------------------------------------


class TestSecretNameMap:
    def test_postgres(self):
        assert _SECRET_NAME_MAP[ServiceType.POSTGRES]("mydb") == "mydb-app"

    def test_mysql(self):
        assert _SECRET_NAME_MAP[ServiceType.MYSQL]("mydb") == "mydb-pxc-secrets"

    def test_mongodb(self):
        assert _SECRET_NAME_MAP[ServiceType.MONGODB]("mydb") == "mydb-psmdb-secrets"

    def test_redis(self):
        assert _SECRET_NAME_MAP[ServiceType.REDIS]("mydb") == "mydb-redis"

    def test_rabbitmq(self):
        assert _SECRET_NAME_MAP[ServiceType.RABBITMQ]("mydb") == "mydb-default-user"


class TestConnectionHintMap:
    def test_postgres(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.POSTGRES]("my-db", "tenant-acme")
        assert "my-db-rw.tenant-acme.svc:5432" in hint
        assert "my_db" in hint  # hyphen → underscore in DB name

    def test_mysql(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.MYSQL]("my-db", "tenant-acme")
        assert "my-db-haproxy.tenant-acme.svc:3306" in hint

    def test_mongodb(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.MONGODB]("my-db", "tenant-acme")
        assert "my-db-mongos.tenant-acme.svc:27017" in hint

    def test_redis(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.REDIS]("my-db", "tenant-acme")
        assert "my-db.tenant-acme.svc:6379" in hint
        assert hint.startswith("redis://")

    def test_rabbitmq(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.RABBITMQ]("my-rmq", "tenant-acme")
        assert "my-rmq.tenant-acme.svc:5672" in hint
        assert hint.startswith("amqp://")


# ---------------------------------------------------------------------------
# ManagedServiceProvisioner
# ---------------------------------------------------------------------------


def _no_everest() -> MagicMock:
    """Return a mock EverestClient that reports as not configured (forces CRD path)."""
    e = MagicMock(spec=EverestClient)
    e.is_configured.return_value = False
    return e


def _make_service(
    name: str = "test-db",
    stype: ServiceType = ServiceType.POSTGRES,
    tier: ServiceTier = ServiceTier.DEV,
) -> ManagedService:
    """Create a transient ManagedService object (no DB session needed)."""
    svc = ManagedService(
        name=name,
        service_type=stype,
        tier=tier,
        status=ServiceStatus.PROVISIONING,
    )
    # Transient objects don't have these set by default
    svc.secret_name = None
    svc.service_namespace = None
    svc.connection_hint = None
    return svc


class TestProvisionerProvision:
    """CRD-based provisioning tests (Everest disabled)."""

    @pytest.mark.asyncio
    async def test_provision_sets_fields(self, mock_k8s_available):
        svc = _make_service()
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.provision(svc, "tenant-acme")

        assert svc.service_namespace == "tenant-acme"
        assert svc.secret_name == "test-db-app"
        assert "test-db-rw.tenant-acme.svc:5432" in svc.connection_hint
        assert svc.status == ServiceStatus.PROVISIONING  # operator will flip to READY later
        mock_k8s_available.custom_objects.create_namespaced_custom_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_provision_mysql(self, mock_k8s_available):
        svc = _make_service(stype=ServiceType.MYSQL)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.provision(svc, "tenant-acme")
        assert svc.secret_name == "test-db-pxc-secrets"
        assert "haproxy" in svc.connection_hint

    @pytest.mark.asyncio
    async def test_provision_mongodb(self, mock_k8s_available):
        svc = _make_service(stype=ServiceType.MONGODB)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.provision(svc, "tenant-acme")
        assert svc.secret_name == "test-db-psmdb-secrets"
        assert "mongos" in svc.connection_hint

    @pytest.mark.asyncio
    async def test_provision_redis(self, mock_k8s_available):
        svc = _make_service(stype=ServiceType.REDIS)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.provision(svc, "tenant-acme")
        assert svc.secret_name == "test-db-redis"
        assert svc.connection_hint.startswith("redis://")

    @pytest.mark.asyncio
    async def test_provision_rabbitmq(self, mock_k8s_available):
        svc = _make_service(stype=ServiceType.RABBITMQ)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.provision(svc, "tenant-acme")
        assert svc.secret_name == "test-db-default-user"
        assert svc.connection_hint.startswith("amqp://")

    @pytest.mark.asyncio
    async def test_provision_k8s_unavailable(self, mock_k8s_unavailable):
        svc = _make_service()
        p = ManagedServiceProvisioner(mock_k8s_unavailable, everest=_no_everest())
        await p.provision(svc, "tenant-acme")
        assert svc.status == ServiceStatus.FAILED
        assert svc.service_namespace is None

    @pytest.mark.asyncio
    async def test_provision_409_conflict_treated_as_idempotent(self, mock_k8s_available):
        """If CRD already exists (409), provision still populates fields."""
        err = ApiException(status=409, reason="AlreadyExists")
        mock_k8s_available.custom_objects.create_namespaced_custom_object.side_effect = err
        svc = _make_service()
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.provision(svc, "tenant-acme")
        # Should NOT be FAILED — idempotent
        assert svc.status == ServiceStatus.PROVISIONING
        assert svc.secret_name is not None

    @pytest.mark.asyncio
    async def test_provision_k8s_error_sets_failed(self, mock_k8s_available):
        err = ApiException(status=500, reason="Internal Error")
        mock_k8s_available.custom_objects.create_namespaced_custom_object.side_effect = err
        svc = _make_service()
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.provision(svc, "tenant-acme")
        assert svc.status == ServiceStatus.FAILED


class TestProvisionerDeprovision:
    """CRD-based deprovision tests (Everest disabled)."""

    @pytest.mark.asyncio
    async def test_deprovision_calls_delete(self, mock_k8s_available):
        svc = _make_service()
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.deprovision(svc)
        mock_k8s_available.custom_objects.delete_namespaced_custom_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_deprovision_no_namespace_is_noop(self, mock_k8s_available):
        svc = _make_service()
        svc.service_namespace = None
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.deprovision(svc)
        mock_k8s_available.custom_objects.delete_namespaced_custom_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_deprovision_k8s_unavailable_is_noop(self, mock_k8s_unavailable):
        svc = _make_service()
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_unavailable, everest=_no_everest())
        await p.deprovision(svc)  # should not raise

    @pytest.mark.asyncio
    async def test_deprovision_404_is_silent(self, mock_k8s_available):
        err = ApiException(status=404, reason="Not Found")
        mock_k8s_available.custom_objects.delete_namespaced_custom_object.side_effect = err
        svc = _make_service()
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.deprovision(svc)  # should not raise


class TestProvisionerSyncStatus:
    """CRD-based sync status tests (Everest disabled)."""

    @pytest.mark.asyncio
    async def test_sync_postgres_healthy(self, mock_k8s_available):
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"phase": "Cluster in healthy state", "readyInstances": 1},
            "spec": {"instances": 1},
        }
        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_sync_postgres_not_yet_ready(self, mock_k8s_available):
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"phase": "Creating", "readyInstances": 0},
            "spec": {"instances": 1},
        }
        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        svc.status = ServiceStatus.PROVISIONING
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.PROVISIONING  # unchanged

    @pytest.mark.asyncio
    async def test_sync_redis_ready(self, mock_k8s_available):
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"readyReplicas": 1},
        }
        svc = _make_service(stype=ServiceType.REDIS)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_sync_mysql_ready(self, mock_k8s_available):
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"state": "ready"},
        }
        svc = _make_service(stype=ServiceType.MYSQL)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_sync_mongodb_ready(self, mock_k8s_available):
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"state": "ready"},
        }
        svc = _make_service(stype=ServiceType.MONGODB)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_sync_rabbitmq_ready(self, mock_k8s_available):
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {
                "conditions": [
                    {"type": "AllReplicasReady", "status": "True"},
                ]
            },
        }
        svc = _make_service(stype=ServiceType.RABBITMQ)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_sync_404_sets_failed(self, mock_k8s_available):
        err = ApiException(status=404, reason="Not Found")
        mock_k8s_available.custom_objects.get_namespaced_custom_object.side_effect = err
        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.FAILED

    @pytest.mark.asyncio
    async def test_sync_k8s_unavailable_is_noop(self, mock_k8s_unavailable):
        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        svc.status = ServiceStatus.PROVISIONING
        p = ManagedServiceProvisioner(mock_k8s_unavailable, everest=_no_everest())
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.PROVISIONING  # unchanged


# ---------------------------------------------------------------------------
# Everest routing logic
# ---------------------------------------------------------------------------


class TestEverestRouting:
    def test_everest_engines_set(self):
        assert ServiceType.POSTGRES in _EVEREST_ENGINES
        assert ServiceType.MYSQL in _EVEREST_ENGINES
        assert ServiceType.MONGODB in _EVEREST_ENGINES
        assert ServiceType.REDIS not in _EVEREST_ENGINES
        assert ServiceType.RABBITMQ not in _EVEREST_ENGINES

    def test_use_everest_when_configured(self, mock_k8s_available):
        everest = MagicMock(spec=EverestClient)
        everest.is_configured.return_value = True
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        assert p._use_everest(ServiceType.POSTGRES) is True
        assert p._use_everest(ServiceType.MYSQL) is True
        assert p._use_everest(ServiceType.MONGODB) is True
        assert p._use_everest(ServiceType.REDIS) is False
        assert p._use_everest(ServiceType.RABBITMQ) is False

    def test_use_everest_false_when_not_configured(self, mock_k8s_available):
        everest = MagicMock(spec=EverestClient)
        everest.is_configured.return_value = False
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        assert p._use_everest(ServiceType.POSTGRES) is False
        assert p._use_everest(ServiceType.MYSQL) is False


# ---------------------------------------------------------------------------
# Everest-based provisioning
# ---------------------------------------------------------------------------


class TestEverestProvision:
    @pytest.mark.asyncio
    async def test_provision_postgres_via_everest(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.return_value = {"metadata": {"name": "acme-test-db"}}

        svc = _make_service(stype=ServiceType.POSTGRES)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        everest.create_database.assert_called_once_with(
            name="acme-test-db", engine_type="postgres", tier="dev"
        )
        assert svc.status == ServiceStatus.PROVISIONING
        assert svc.everest_name == "acme-test-db"
        assert svc.service_namespace == "everest"
        assert svc.secret_name == "everest-secrets-acme-test-db"
        assert svc.connection_hint is not None
        mock_k8s_available.custom_objects.create_namespaced_custom_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_provision_mysql_via_everest(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.return_value = {"metadata": {"name": "acme-test-db"}}

        svc = _make_service(stype=ServiceType.MYSQL)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        everest.create_database.assert_called_once_with(
            name="acme-test-db", engine_type="mysql", tier="dev"
        )
        assert svc.status == ServiceStatus.PROVISIONING
        assert svc.everest_name == "acme-test-db"

    @pytest.mark.asyncio
    async def test_provision_mongodb_via_everest(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.return_value = {"metadata": {"name": "acme-test-db"}}

        svc = _make_service(stype=ServiceType.MONGODB)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        everest.create_database.assert_called_once_with(
            name="acme-test-db", engine_type="mongodb", tier="dev"
        )

    @pytest.mark.asyncio
    async def test_provision_prod_tier_via_everest(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.return_value = {"metadata": {"name": "acme-prod-db"}}

        svc = _make_service(name="prod-db", stype=ServiceType.POSTGRES, tier=ServiceTier.PROD)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        everest.create_database.assert_called_once_with(
            name="acme-prod-db", engine_type="postgres", tier="prod"
        )

    @pytest.mark.asyncio
    async def test_everest_failure_falls_back_to_crd(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.side_effect = Exception("Everest unreachable")

        svc = _make_service(stype=ServiceType.POSTGRES)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        mock_k8s_available.custom_objects.create_namespaced_custom_object.assert_called_once()
        assert svc.status == ServiceStatus.PROVISIONING
        assert svc.service_namespace == "tenant-acme"
        assert svc.everest_name is None  # CRD fallback, no everest_name

    @pytest.mark.asyncio
    async def test_redis_always_uses_crd_even_with_everest(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True

        svc = _make_service(stype=ServiceType.REDIS)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        everest.create_database.assert_not_called()
        mock_k8s_available.custom_objects.create_namespaced_custom_object.assert_called_once()


class TestEverestSyncStatus:
    @pytest.mark.asyncio
    async def test_sync_postgres_ready_via_everest(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_status.return_value = "ready"

        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.sync_status(svc)

        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_sync_postgres_error_via_everest(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_status.return_value = "error"

        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.sync_status(svc)

        assert svc.status == ServiceStatus.FAILED

    @pytest.mark.asyncio
    async def test_sync_not_found_via_everest(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_status.return_value = "not_found"

        svc = _make_service(stype=ServiceType.MYSQL)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.sync_status(svc)

        assert svc.status == ServiceStatus.FAILED

    @pytest.mark.asyncio
    async def test_sync_initializing_keeps_provisioning(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_status.return_value = "initializing"

        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        svc.status = ServiceStatus.PROVISIONING
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.sync_status(svc)

        assert svc.status == ServiceStatus.PROVISIONING  # unchanged

    @pytest.mark.asyncio
    async def test_sync_everest_error_is_noop(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_status.side_effect = Exception("Connection refused")

        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        svc.status = ServiceStatus.PROVISIONING
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.sync_status(svc)

        assert svc.status == ServiceStatus.PROVISIONING  # unchanged on error


class TestEverestUpdate:
    @pytest.mark.asyncio
    async def test_update_postgres_via_everest(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True

        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "everest"
        svc.status = ServiceStatus.READY
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.update(svc, storage="5Gi", cpu="1")

        everest.update_database.assert_called_once_with(
            "test-db", replicas=None, storage="5Gi", cpu="1", memory=None
        )

    @pytest.mark.asyncio
    async def test_update_redis_logs_warning(self, mock_k8s_available):
        """Redis uses CRDs — update not implemented, should just log warning."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True

        svc = _make_service(stype=ServiceType.REDIS)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.update(svc, storage="5Gi")  # should not raise

        everest.update_database.assert_not_called()


class TestEverestDeprovision:
    @pytest.mark.asyncio
    async def test_deprovision_via_everest(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True

        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.deprovision(svc)

        everest.delete_database.assert_called_once_with("test-db")
        mock_k8s_available.custom_objects.delete_namespaced_custom_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_deprovision_everest_error_logged(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.delete_database.side_effect = Exception("Everest error")

        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.deprovision(svc)  # should not raise

    @pytest.mark.asyncio
    async def test_deprovision_redis_uses_crd(self, mock_k8s_available):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True

        svc = _make_service(stype=ServiceType.REDIS)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.deprovision(svc)

        everest.delete_database.assert_not_called()
        mock_k8s_available.custom_objects.delete_namespaced_custom_object.assert_called_once()


# ---------------------------------------------------------------------------
# Sprint B: PostgreSQL connection_hint and namespace verification
# ---------------------------------------------------------------------------


class TestEverestPostgresConnectionDetails:
    """Verify that Everest provisioning sets correct connection_hint, namespace, and secret_name."""

    @pytest.mark.asyncio
    async def test_everest_pg_connection_hint_has_prefixed_name(self, mock_k8s_available):
        """connection_hint must use tenant-prefixed DB name in Everest namespace."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.return_value = {"metadata": {"name": "acme-my-pg"}}

        svc = _make_service(name="my-pg", stype=ServiceType.POSTGRES)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        assert svc.connection_hint is not None
        assert svc.connection_hint.startswith("postgresql://")
        assert ".everest.svc:" in svc.connection_hint
        # Must contain the prefixed name (tenant-service)
        assert "acme-my-pg" in svc.connection_hint
        # Everest was called with prefixed name
        everest.create_database.assert_called_once_with(
            name="acme-my-pg", engine_type="postgres", tier="dev"
        )

    @pytest.mark.asyncio
    async def test_everest_pg_sets_everest_name_field(self, mock_k8s_available):
        """Provision must store everest_name = '{tenant_slug}-{service_name}'."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.return_value = {"metadata": {"name": "acme-pg-1"}}

        svc = _make_service(name="pg-1", stype=ServiceType.POSTGRES)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        assert svc.everest_name == "acme-pg-1"
        assert svc.service_namespace == "everest"
        assert svc.secret_name == "everest-secrets-acme-pg-1"

    @pytest.mark.asyncio
    async def test_crd_fallback_uses_tenant_namespace(self, mock_k8s_available):
        """When Everest fails, CRD fallback must use tenant namespace, not everest."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.side_effect = Exception("Everest down")

        svc = _make_service(name="pg-fallback", stype=ServiceType.POSTGRES)
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.provision(svc, "tenant-fallback", tenant_slug="fallback")

        # CRD fallback: namespace = tenant, secret = CNPG convention, no everest_name
        assert svc.service_namespace == "tenant-fallback"
        assert svc.secret_name == "pg-fallback-app"
        assert ".tenant-fallback.svc:" in svc.connection_hint
        assert svc.everest_name is None

    @pytest.mark.asyncio
    async def test_everest_sync_uses_everest_name(self, mock_k8s_available):
        """sync_details must use service.everest_name for Everest API calls."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_details.return_value = {
            "status": "ready",
            "engine_version": "17.7",
            "replicas": 1,
            "ready_replicas": 1,
            "storage": "1Gi",
            "cpu": "600m",
            "memory": "512Mi",
            "hostname": "acme-pg-2-rw.everest.svc",
            "port": 5432,
        }

        svc = _make_service(name="pg-2", stype=ServiceType.POSTGRES)
        svc.everest_name = "acme-pg-2"
        svc.status = ServiceStatus.PROVISIONING
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        details = await p.sync_details(svc)

        assert details is not None
        assert svc.status == ServiceStatus.READY
        # Must call Everest with the prefixed name
        everest.get_database_details.assert_called_once_with("acme-pg-2")

    @pytest.mark.asyncio
    async def test_everest_deprovision_uses_everest_name(self, mock_k8s_available):
        """deprovision must use service.everest_name for Everest API calls."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True

        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.everest_name = "acme-test-db"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=everest)
        await p.deprovision(svc)

        everest.delete_database.assert_called_once_with("acme-test-db")


# ---------------------------------------------------------------------------
# Pod-based health check (_sync_from_pod) + DEGRADED status (Sprint C1.5)
# ---------------------------------------------------------------------------


def _mock_pod(phase: str = "Running", ready: bool = True, restart_reason: str | None = None, waiting_reason: str | None = None):
    """Build a mock K8s Pod object with configurable status."""
    pod = MagicMock()
    pod.status.phase = phase

    container = MagicMock()
    container.ready = ready

    # Set up last_state.terminated
    if restart_reason:
        terminated = MagicMock()
        terminated.reason = restart_reason
        container.last_state.terminated = terminated
    else:
        container.last_state = MagicMock()
        container.last_state.terminated = None

    # Set up state.waiting
    if waiting_reason:
        waiting = MagicMock()
        waiting.reason = waiting_reason
        container.state.waiting = waiting
    else:
        container.state = MagicMock()
        container.state.waiting = None

    pod.status.container_statuses = [container]
    return pod


class TestSyncFromPod:
    """Tests for _sync_from_pod fallback health check."""

    @pytest.mark.asyncio
    async def test_pod_running_and_ready_sets_ready(self, mock_k8s_available):
        """Pod Running + all containers ready → service READY."""
        mock_k8s_available.core_v1.read_namespaced_pod.return_value = _mock_pod(
            phase="Running", ready=True
        )

        svc = _make_service(name="my-redis", stype=ServiceType.REDIS)
        svc.service_namespace = "tenant-test"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        p._sync_from_pod(svc, "my-redis-0")

        assert svc.status == ServiceStatus.READY
        assert svc.error_message is None

    @pytest.mark.asyncio
    async def test_pod_oomkilled_sets_degraded_from_ready(self, mock_k8s_available):
        """Pod OOMKilled when service was READY → DEGRADED with error message."""
        mock_k8s_available.core_v1.read_namespaced_pod.return_value = _mock_pod(
            phase="Running", ready=False, restart_reason="OOMKilled"
        )

        svc = _make_service(name="my-redis", stype=ServiceType.REDIS)
        svc.service_namespace = "tenant-test"
        svc.status = ServiceStatus.READY  # was ready before
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        p._sync_from_pod(svc, "my-redis-0")

        assert svc.status == ServiceStatus.DEGRADED
        assert "memory" in svc.error_message.lower()

    @pytest.mark.asyncio
    async def test_pod_crashloop_sets_failed_from_provisioning(self, mock_k8s_available):
        """Pod CrashLoopBackOff during provisioning → FAILED."""
        mock_k8s_available.core_v1.read_namespaced_pod.return_value = _mock_pod(
            phase="Running", ready=False, waiting_reason="CrashLoopBackOff"
        )

        svc = _make_service(name="my-redis", stype=ServiceType.REDIS)
        svc.service_namespace = "tenant-test"
        svc.status = ServiceStatus.PROVISIONING
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        p._sync_from_pod(svc, "my-redis-0")

        assert svc.status == ServiceStatus.FAILED
        assert "crashing" in svc.error_message.lower()

    @pytest.mark.asyncio
    async def test_pod_not_found_sets_degraded_from_ready(self, mock_k8s_available):
        """Pod 404 when service was READY → DEGRADED."""
        mock_k8s_available.core_v1.read_namespaced_pod.side_effect = ApiException(status=404)

        svc = _make_service(name="my-redis", stype=ServiceType.REDIS)
        svc.service_namespace = "tenant-test"
        svc.status = ServiceStatus.READY
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        p._sync_from_pod(svc, "my-redis-0")

        assert svc.status == ServiceStatus.DEGRADED
        assert "not found" in svc.error_message.lower()

    @pytest.mark.asyncio
    async def test_pod_not_found_keeps_provisioning(self, mock_k8s_available):
        """Pod 404 during provisioning → stay provisioning (pod not created yet)."""
        mock_k8s_available.core_v1.read_namespaced_pod.side_effect = ApiException(status=404)

        svc = _make_service(name="my-redis", stype=ServiceType.REDIS)
        svc.service_namespace = "tenant-test"
        svc.status = ServiceStatus.PROVISIONING
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        p._sync_from_pod(svc, "my-redis-0")

        assert svc.status == ServiceStatus.PROVISIONING  # unchanged

    @pytest.mark.asyncio
    async def test_redis_sync_uses_pod_check(self, mock_k8s_available):
        """Redis CRD sync with empty status falls back to pod check."""
        # CRD returns empty status
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {},
            "spec": {},
        }
        # Pod is running and ready
        mock_k8s_available.core_v1.read_namespaced_pod.return_value = _mock_pod(
            phase="Running", ready=True
        )

        svc = _make_service(name="my-redis", stype=ServiceType.REDIS)
        svc.service_namespace = "tenant-test"
        p = ManagedServiceProvisioner(mock_k8s_available, everest=_no_everest())
        await p.sync_status(svc)

        assert svc.status == ServiceStatus.READY
