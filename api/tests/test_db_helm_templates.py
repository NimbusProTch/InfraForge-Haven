"""Tests for chart_values_service: DB Helm values builders."""

import pytest

from app.services.chart_values_service import (
    DbPlan,
    build_mongodb_values,
    build_mysql_values,
    build_pg_values,
    build_rabbitmq_values,
    build_redis_values,
    build_service_values,
)

# ---------------------------------------------------------------------------
# PostgreSQL (haven-pg)
# ---------------------------------------------------------------------------


class TestBuildPgValues:
    def test_small_plan_defaults(self):
        v = build_pg_values("my-db", "tenant-acme")
        assert v["name"] == "my-db"
        assert v["namespace"] == "tenant-acme"
        assert v["plan"] == "small"
        assert v["postgres"]["instances"] == 1
        assert v["postgres"]["storage"] == "5Gi"
        assert v["postgres"]["version"] == "16"

    def test_medium_plan(self):
        v = build_pg_values("my-db", "tenant-acme", plan=DbPlan.MEDIUM)
        assert v["postgres"]["instances"] == 2
        assert v["postgres"]["storage"] == "20Gi"
        assert v["plan"] == "medium"

    def test_large_plan(self):
        v = build_pg_values("my-db", "tenant-acme", plan=DbPlan.LARGE)
        assert v["postgres"]["instances"] == 3
        assert v["postgres"]["storage"] == "100Gi"

    def test_backup_enabled(self):
        v = build_pg_values("my-db", "tenant-acme", backup_enabled=True, backup_bucket="backups-acme")
        assert v["backup"]["enabled"] is True
        assert v["backup"]["bucket"] == "backups-acme"
        assert v["backup"]["schedule"] == "0 2 * * *"

    def test_backup_disabled_by_default(self):
        v = build_pg_values("my-db", "tenant-acme")
        assert v["backup"]["enabled"] is False

    def test_custom_storage_class(self):
        v = build_pg_values("my-db", "tenant-acme", storage_class="ceph-rbd")
        assert v["postgres"]["storageClass"] == "ceph-rbd"

    def test_resources_present(self):
        v = build_pg_values("my-db", "tenant-acme")
        res = v["postgres"]["resources"]
        assert "requests" in res
        assert "limits" in res
        assert "cpu" in res["requests"]
        assert "memory" in res["requests"]


# ---------------------------------------------------------------------------
# MySQL (haven-mysql)
# ---------------------------------------------------------------------------


class TestBuildMysqlValues:
    def test_small_plan_defaults(self):
        v = build_mysql_values("my-mysql", "tenant-acme")
        assert v["name"] == "my-mysql"
        assert v["namespace"] == "tenant-acme"
        assert v["plan"] == "small"
        assert v["mysql"]["instances"] == 1
        assert v["mysql"]["storage"] == "5Gi"
        assert v["mysql"]["allowUnsafeConfigurations"] is True

    def test_medium_plan_safe(self):
        v = build_mysql_values("my-mysql", "tenant-acme", plan=DbPlan.MEDIUM)
        assert v["mysql"]["instances"] == 3
        assert v["mysql"]["allowUnsafeConfigurations"] is False

    def test_large_plan(self):
        v = build_mysql_values("my-mysql", "tenant-acme", plan=DbPlan.LARGE)
        assert v["mysql"]["storage"] == "100Gi"
        assert v["mysql"]["allowUnsafeConfigurations"] is False

    def test_custom_version(self):
        v = build_mysql_values("my-mysql", "tenant-acme", mysql_version="8.4")
        assert v["mysql"]["version"] == "8.4"


# ---------------------------------------------------------------------------
# MongoDB (haven-mongodb)
# ---------------------------------------------------------------------------


class TestBuildMongodbValues:
    def test_small_plan_defaults(self):
        v = build_mongodb_values("my-mongo", "tenant-acme")
        assert v["name"] == "my-mongo"
        assert v["namespace"] == "tenant-acme"
        assert v["plan"] == "small"
        assert v["mongodb"]["instances"] == 1
        assert v["mongodb"]["storage"] == "5Gi"
        assert v["mongodb"]["allowUnsafeConfigurations"] is True

    def test_medium_plan(self):
        v = build_mongodb_values("my-mongo", "tenant-acme", plan=DbPlan.MEDIUM)
        assert v["mongodb"]["instances"] == 3
        assert v["mongodb"]["allowUnsafeConfigurations"] is False

    def test_large_plan_storage(self):
        v = build_mongodb_values("my-mongo", "tenant-acme", plan=DbPlan.LARGE)
        assert v["mongodb"]["storage"] == "100Gi"

    def test_custom_mongo_version(self):
        v = build_mongodb_values("my-mongo", "tenant-acme", mongo_version="6.0")
        assert v["mongodb"]["version"] == "6.0"


# ---------------------------------------------------------------------------
# Redis (haven-redis)
# ---------------------------------------------------------------------------


class TestBuildRedisValues:
    def test_small_plan_defaults(self):
        v = build_redis_values("my-redis", "tenant-acme")
        assert v["name"] == "my-redis"
        assert v["namespace"] == "tenant-acme"
        assert v["plan"] == "small"
        assert v["redis"]["storage"] == "1Gi"
        assert "opstree/redis" in v["redis"]["image"]

    def test_medium_plan(self):
        v = build_redis_values("my-redis", "tenant-acme", plan=DbPlan.MEDIUM)
        assert v["redis"]["storage"] == "5Gi"

    def test_large_plan(self):
        v = build_redis_values("my-redis", "tenant-acme", plan=DbPlan.LARGE)
        assert v["redis"]["storage"] == "20Gi"

    def test_resources_present(self):
        v = build_redis_values("my-redis", "tenant-acme")
        assert "resources" in v["redis"]
        assert "requests" in v["redis"]["resources"]
        assert "limits" in v["redis"]["resources"]

    def test_custom_storage_class(self):
        v = build_redis_values("my-redis", "tenant-acme", storage_class="nfs-client")
        assert v["redis"]["storageClass"] == "nfs-client"


# ---------------------------------------------------------------------------
# RabbitMQ (haven-rabbitmq)
# ---------------------------------------------------------------------------


class TestBuildRabbitmqValues:
    def test_small_plan_defaults(self):
        v = build_rabbitmq_values("my-rmq", "tenant-acme")
        assert v["name"] == "my-rmq"
        assert v["namespace"] == "tenant-acme"
        assert v["plan"] == "small"
        assert v["rabbitmq"]["replicas"] == 1
        assert v["rabbitmq"]["storage"] == "5Gi"

    def test_medium_plan(self):
        v = build_rabbitmq_values("my-rmq", "tenant-acme", plan=DbPlan.MEDIUM)
        assert v["rabbitmq"]["replicas"] == 3
        assert v["rabbitmq"]["storage"] == "10Gi"

    def test_large_plan(self):
        v = build_rabbitmq_values("my-rmq", "tenant-acme", plan=DbPlan.LARGE)
        assert v["rabbitmq"]["storage"] == "50Gi"

    def test_resources_present(self):
        v = build_rabbitmq_values("my-rmq", "tenant-acme")
        assert "resources" in v["rabbitmq"]


# ---------------------------------------------------------------------------
# Dispatcher: build_service_values
# ---------------------------------------------------------------------------


class TestBuildServiceValues:
    def test_dispatch_postgres(self):
        v = build_service_values("postgres", "pg-db", "tenant-acme")
        assert "postgres" in v

    def test_dispatch_mysql(self):
        v = build_service_values("mysql", "mysql-db", "tenant-acme")
        assert "mysql" in v

    def test_dispatch_mongodb(self):
        v = build_service_values("mongodb", "mongo-db", "tenant-acme")
        assert "mongodb" in v

    def test_dispatch_redis(self):
        v = build_service_values("redis", "redis-db", "tenant-acme")
        assert "redis" in v

    def test_dispatch_rabbitmq(self):
        v = build_service_values("rabbitmq", "rmq", "tenant-acme")
        assert "rabbitmq" in v

    def test_dispatch_with_plan(self):
        v = build_service_values("postgres", "pg-db", "tenant-acme", plan=DbPlan.LARGE)
        assert v["postgres"]["instances"] == 3

    def test_unknown_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown service type"):
            build_service_values("cassandra", "db", "ns")

    def test_all_values_contain_name_and_namespace(self):
        for stype in ("postgres", "mysql", "mongodb", "redis", "rabbitmq"):
            v = build_service_values(stype, f"svc-{stype}", "tenant-x")
            assert v["name"] == f"svc-{stype}"
            assert v["namespace"] == "tenant-x"

    def test_postgres_backup_kwarg_passthrough(self):
        v = build_service_values("postgres", "pg", "ns", backup_enabled=True, backup_bucket="bkt")
        assert v["backup"]["enabled"] is True
        assert v["backup"]["bucket"] == "bkt"

    def test_plan_string_coercion(self):
        # DbPlan enum and string both work via dispatcher
        v1 = build_service_values("redis", "r", "ns", plan=DbPlan.MEDIUM)
        v2 = build_redis_values("r", "ns", plan=DbPlan.MEDIUM)
        assert v1["redis"]["storage"] == v2["redis"]["storage"]
