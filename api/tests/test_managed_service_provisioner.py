"""Unit tests for ManagedServiceProvisioner and CRD body builders."""

import pytest
from kubernetes.client.exceptions import ApiException

from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType
from app.services.managed_service import (
    _CONNECTION_HINT_MAP,
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
        storage_size = body["spec"]["storage"]["volumeClaimTemplate"]["spec"]["resources"]["requests"]["storage"]
        assert storage_size == "1Gi"

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
        assert "my-db-redis.tenant-acme.svc:6379" in hint
        assert hint.startswith("redis://")

    def test_rabbitmq(self):
        hint = _CONNECTION_HINT_MAP[ServiceType.RABBITMQ]("my-rmq", "tenant-acme")
        assert "my-rmq.tenant-acme.svc:5672" in hint
        assert hint.startswith("amqp://")


# ---------------------------------------------------------------------------
# ManagedServiceProvisioner
# ---------------------------------------------------------------------------


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
    @pytest.mark.asyncio
    async def test_provision_sets_fields(self, mock_k8s_available):
        svc = _make_service()
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.provision(svc, "tenant-acme")

        assert svc.service_namespace == "tenant-acme"
        assert svc.secret_name == "test-db-app"
        assert "test-db-rw.tenant-acme.svc:5432" in svc.connection_hint
        assert svc.status == ServiceStatus.PROVISIONING  # operator will flip to READY later
        mock_k8s_available.custom_objects.create_namespaced_custom_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_provision_mysql(self, mock_k8s_available):
        svc = _make_service(stype=ServiceType.MYSQL)
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.provision(svc, "tenant-acme")
        assert svc.secret_name == "test-db-pxc-secrets"
        assert "haproxy" in svc.connection_hint

    @pytest.mark.asyncio
    async def test_provision_mongodb(self, mock_k8s_available):
        svc = _make_service(stype=ServiceType.MONGODB)
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.provision(svc, "tenant-acme")
        assert svc.secret_name == "test-db-psmdb-secrets"
        assert "mongos" in svc.connection_hint

    @pytest.mark.asyncio
    async def test_provision_redis(self, mock_k8s_available):
        svc = _make_service(stype=ServiceType.REDIS)
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.provision(svc, "tenant-acme")
        assert svc.secret_name == "test-db-redis"
        assert svc.connection_hint.startswith("redis://")

    @pytest.mark.asyncio
    async def test_provision_rabbitmq(self, mock_k8s_available):
        svc = _make_service(stype=ServiceType.RABBITMQ)
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.provision(svc, "tenant-acme")
        assert svc.secret_name == "test-db-default-user"
        assert svc.connection_hint.startswith("amqp://")

    @pytest.mark.asyncio
    async def test_provision_k8s_unavailable(self, mock_k8s_unavailable):
        svc = _make_service()
        p = ManagedServiceProvisioner(mock_k8s_unavailable)
        await p.provision(svc, "tenant-acme")
        assert svc.status == ServiceStatus.FAILED
        assert svc.service_namespace is None

    @pytest.mark.asyncio
    async def test_provision_409_conflict_treated_as_idempotent(self, mock_k8s_available):
        """If CRD already exists (409), provision still populates fields."""
        err = ApiException(status=409, reason="AlreadyExists")
        mock_k8s_available.custom_objects.create_namespaced_custom_object.side_effect = err
        svc = _make_service()
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.provision(svc, "tenant-acme")
        # Should NOT be FAILED — idempotent
        assert svc.status == ServiceStatus.PROVISIONING
        assert svc.secret_name is not None

    @pytest.mark.asyncio
    async def test_provision_k8s_error_sets_failed(self, mock_k8s_available):
        err = ApiException(status=500, reason="Internal Error")
        mock_k8s_available.custom_objects.create_namespaced_custom_object.side_effect = err
        svc = _make_service()
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.provision(svc, "tenant-acme")
        assert svc.status == ServiceStatus.FAILED


class TestProvisionerDeprovision:
    @pytest.mark.asyncio
    async def test_deprovision_calls_delete(self, mock_k8s_available):
        svc = _make_service()
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.deprovision(svc)
        mock_k8s_available.custom_objects.delete_namespaced_custom_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_deprovision_no_namespace_is_noop(self, mock_k8s_available):
        svc = _make_service()
        svc.service_namespace = None
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.deprovision(svc)
        mock_k8s_available.custom_objects.delete_namespaced_custom_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_deprovision_k8s_unavailable_is_noop(self, mock_k8s_unavailable):
        svc = _make_service()
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_unavailable)
        await p.deprovision(svc)  # should not raise

    @pytest.mark.asyncio
    async def test_deprovision_404_is_silent(self, mock_k8s_available):
        err = ApiException(status=404, reason="Not Found")
        mock_k8s_available.custom_objects.delete_namespaced_custom_object.side_effect = err
        svc = _make_service()
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.deprovision(svc)  # should not raise


class TestProvisionerSyncStatus:
    @pytest.mark.asyncio
    async def test_sync_postgres_healthy(self, mock_k8s_available):
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"phase": "Cluster in healthy state", "readyInstances": 1},
            "spec": {"instances": 1},
        }
        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available)
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
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.PROVISIONING  # unchanged

    @pytest.mark.asyncio
    async def test_sync_redis_ready(self, mock_k8s_available):
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"readyReplicas": 1},
        }
        svc = _make_service(stype=ServiceType.REDIS)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_sync_mysql_ready(self, mock_k8s_available):
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"state": "ready"},
        }
        svc = _make_service(stype=ServiceType.MYSQL)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_sync_mongodb_ready(self, mock_k8s_available):
        mock_k8s_available.custom_objects.get_namespaced_custom_object.return_value = {
            "status": {"state": "ready"},
        }
        svc = _make_service(stype=ServiceType.MONGODB)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available)
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
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.READY

    @pytest.mark.asyncio
    async def test_sync_404_sets_failed(self, mock_k8s_available):
        err = ApiException(status=404, reason="Not Found")
        mock_k8s_available.custom_objects.get_namespaced_custom_object.side_effect = err
        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        p = ManagedServiceProvisioner(mock_k8s_available)
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.FAILED

    @pytest.mark.asyncio
    async def test_sync_k8s_unavailable_is_noop(self, mock_k8s_unavailable):
        svc = _make_service(stype=ServiceType.POSTGRES)
        svc.service_namespace = "tenant-acme"
        svc.status = ServiceStatus.PROVISIONING
        p = ManagedServiceProvisioner(mock_k8s_unavailable)
        await p.sync_status(svc)
        assert svc.status == ServiceStatus.PROVISIONING  # unchanged
