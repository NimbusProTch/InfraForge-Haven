"""Chart values service: builds Helm values.yaml dicts for managed DB charts.

Each haven-{pg,mysql,mongodb,redis,rabbitmq} chart accepts a standardised
values structure. This service constructs those dicts from service metadata
so the GitOps scaffold can push them to Gitea.

Plan presets (small / medium / large) provide sensible defaults for each tier.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class DbPlan(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


# ---------------------------------------------------------------------------
# Plan definitions per DB type
# ---------------------------------------------------------------------------

_PG_PLANS: dict[DbPlan, dict[str, Any]] = {
    DbPlan.SMALL: {
        "instances": 1,
        "storage": "5Gi",
        "cpu_request": "100m",
        "cpu_limit": "500m",
        "memory_request": "128Mi",
        "memory_limit": "512Mi",
    },
    DbPlan.MEDIUM: {
        "instances": 2,
        "storage": "20Gi",
        "cpu_request": "250m",
        "cpu_limit": "1000m",
        "memory_request": "256Mi",
        "memory_limit": "1Gi",
    },
    DbPlan.LARGE: {
        "instances": 3,
        "storage": "100Gi",
        "cpu_request": "500m",
        "cpu_limit": "2000m",
        "memory_request": "512Mi",
        "memory_limit": "4Gi",
    },
}

_MYSQL_PLANS: dict[DbPlan, dict[str, Any]] = {
    DbPlan.SMALL: {
        "instances": 1,
        "storage": "5Gi",
        "cpu_request": "100m",
        "cpu_limit": "500m",
        "memory_request": "256Mi",
        "memory_limit": "1Gi",
        "allow_unsafe": True,
    },
    DbPlan.MEDIUM: {
        "instances": 3,
        "storage": "20Gi",
        "cpu_request": "250m",
        "cpu_limit": "1000m",
        "memory_request": "512Mi",
        "memory_limit": "2Gi",
        "allow_unsafe": False,
    },
    DbPlan.LARGE: {
        "instances": 3,
        "storage": "100Gi",
        "cpu_request": "500m",
        "cpu_limit": "2000m",
        "memory_request": "1Gi",
        "memory_limit": "4Gi",
        "allow_unsafe": False,
    },
}

_MONGODB_PLANS: dict[DbPlan, dict[str, Any]] = {
    DbPlan.SMALL: {
        "instances": 1,
        "storage": "5Gi",
        "cpu_request": "100m",
        "cpu_limit": "500m",
        "memory_request": "256Mi",
        "memory_limit": "512Mi",
        "allow_unsafe": True,
    },
    DbPlan.MEDIUM: {
        "instances": 3,
        "storage": "20Gi",
        "cpu_request": "250m",
        "cpu_limit": "1000m",
        "memory_request": "512Mi",
        "memory_limit": "2Gi",
        "allow_unsafe": False,
    },
    DbPlan.LARGE: {
        "instances": 3,
        "storage": "100Gi",
        "cpu_request": "500m",
        "cpu_limit": "2000m",
        "memory_request": "1Gi",
        "memory_limit": "8Gi",
        "allow_unsafe": False,
    },
}

_REDIS_PLANS: dict[DbPlan, dict[str, Any]] = {
    DbPlan.SMALL: {
        "storage": "1Gi",
        "image": "quay.io/opstree/redis:v7.0.15",
        "cpu_request": "50m",
        "cpu_limit": "200m",
        "memory_request": "64Mi",
        "memory_limit": "256Mi",
    },
    DbPlan.MEDIUM: {
        "storage": "5Gi",
        "image": "quay.io/opstree/redis:v7.0.15",
        "cpu_request": "100m",
        "cpu_limit": "500m",
        "memory_request": "128Mi",
        "memory_limit": "512Mi",
    },
    DbPlan.LARGE: {
        "storage": "20Gi",
        "image": "quay.io/opstree/redis:v7.0.15",
        "cpu_request": "250m",
        "cpu_limit": "1000m",
        "memory_request": "256Mi",
        "memory_limit": "2Gi",
    },
}

_RABBITMQ_PLANS: dict[DbPlan, dict[str, Any]] = {
    DbPlan.SMALL: {
        "replicas": 1,
        "storage": "5Gi",
        "cpu_request": "100m",
        "cpu_limit": "500m",
        "memory_request": "128Mi",
        "memory_limit": "512Mi",
    },
    DbPlan.MEDIUM: {
        "replicas": 3,
        "storage": "10Gi",
        "cpu_request": "250m",
        "cpu_limit": "1000m",
        "memory_request": "256Mi",
        "memory_limit": "1Gi",
    },
    DbPlan.LARGE: {
        "replicas": 3,
        "storage": "50Gi",
        "cpu_request": "500m",
        "cpu_limit": "2000m",
        "memory_request": "512Mi",
        "memory_limit": "2Gi",
    },
}


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_pg_values(
    name: str,
    namespace: str,
    plan: DbPlan = DbPlan.SMALL,
    pg_version: str = "16",
    storage_class: str = "longhorn",
    backup_enabled: bool = False,
    backup_bucket: str = "",
    backup_schedule: str = "0 2 * * *",
) -> dict[str, Any]:
    """Build haven-pg chart values."""
    p = _PG_PLANS[plan]
    values: dict[str, Any] = {
        "name": name,
        "namespace": namespace,
        "plan": plan.value,
        "postgres": {
            "version": pg_version,
            "instances": p["instances"],
            "storage": p["storage"],
            "storageClass": storage_class,
            "resources": {
                "requests": {"cpu": p["cpu_request"], "memory": p["memory_request"]},
                "limits": {"cpu": p["cpu_limit"], "memory": p["memory_limit"]},
            },
        },
        "backup": {
            "enabled": backup_enabled,
            "bucket": backup_bucket,
            "schedule": backup_schedule,
        },
    }
    return values


def build_mysql_values(
    name: str,
    namespace: str,
    plan: DbPlan = DbPlan.SMALL,
    mysql_version: str = "8.0",
    storage_class: str = "longhorn",
) -> dict[str, Any]:
    """Build haven-mysql chart values."""
    p = _MYSQL_PLANS[plan]
    return {
        "name": name,
        "namespace": namespace,
        "plan": plan.value,
        "mysql": {
            "version": mysql_version,
            "instances": p["instances"],
            "storage": p["storage"],
            "storageClass": storage_class,
            "allowUnsafeConfigurations": p["allow_unsafe"],
            "resources": {
                "requests": {"cpu": p["cpu_request"], "memory": p["memory_request"]},
                "limits": {"cpu": p["cpu_limit"], "memory": p["memory_limit"]},
            },
        },
    }


def build_mongodb_values(
    name: str,
    namespace: str,
    plan: DbPlan = DbPlan.SMALL,
    mongo_version: str = "7.0",
    storage_class: str = "longhorn",
) -> dict[str, Any]:
    """Build haven-mongodb chart values."""
    p = _MONGODB_PLANS[plan]
    return {
        "name": name,
        "namespace": namespace,
        "plan": plan.value,
        "mongodb": {
            "version": mongo_version,
            "instances": p["instances"],
            "storage": p["storage"],
            "storageClass": storage_class,
            "allowUnsafeConfigurations": p["allow_unsafe"],
            "resources": {
                "requests": {"cpu": p["cpu_request"], "memory": p["memory_request"]},
                "limits": {"cpu": p["cpu_limit"], "memory": p["memory_limit"]},
            },
        },
    }


def build_redis_values(
    name: str,
    namespace: str,
    plan: DbPlan = DbPlan.SMALL,
    storage_class: str = "longhorn",
) -> dict[str, Any]:
    """Build haven-redis chart values."""
    p = _REDIS_PLANS[plan]
    return {
        "name": name,
        "namespace": namespace,
        "plan": plan.value,
        "redis": {
            "image": p["image"],
            "storage": p["storage"],
            "storageClass": storage_class,
            "resources": {
                "requests": {"cpu": p["cpu_request"], "memory": p["memory_request"]},
                "limits": {"cpu": p["cpu_limit"], "memory": p["memory_limit"]},
            },
        },
    }


def build_rabbitmq_values(
    name: str,
    namespace: str,
    plan: DbPlan = DbPlan.SMALL,
    storage_class: str = "longhorn",
) -> dict[str, Any]:
    """Build haven-rabbitmq chart values."""
    p = _RABBITMQ_PLANS[plan]
    return {
        "name": name,
        "namespace": namespace,
        "plan": plan.value,
        "rabbitmq": {
            "replicas": p["replicas"],
            "storage": p["storage"],
            "storageClass": storage_class,
            "resources": {
                "requests": {"cpu": p["cpu_request"], "memory": p["memory_request"]},
                "limits": {"cpu": p["cpu_limit"], "memory": p["memory_limit"]},
            },
        },
    }


# ---------------------------------------------------------------------------
# Dispatcher — resolves service type → builder
# ---------------------------------------------------------------------------

_BUILDERS = {
    "postgres": build_pg_values,
    "mysql": build_mysql_values,
    "mongodb": build_mongodb_values,
    "redis": build_redis_values,
    "rabbitmq": build_rabbitmq_values,
}


def build_service_values(
    service_type: str,
    name: str,
    namespace: str,
    plan: DbPlan = DbPlan.SMALL,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build chart values for any supported service type.

    Args:
        service_type: One of postgres | mysql | mongodb | redis | rabbitmq
        name:         K8s resource name
        namespace:    Target namespace
        plan:         Resource plan (small | medium | large)
        **kwargs:     Passed through to the type-specific builder

    Raises:
        ValueError: If service_type is not recognised.
    """
    builder = _BUILDERS.get(service_type)
    if builder is None:
        raise ValueError(f"Unknown service type: {service_type!r}. Supported: {list(_BUILDERS)}")
    return builder(name=name, namespace=namespace, plan=plan, **kwargs)
