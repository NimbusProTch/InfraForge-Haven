"""Builds Helm values dicts for tenant apps and managed services.

Used by the GitOps service to generate values.yaml content that
the ArgoCD ApplicationSet picks up and syncs to the cluster.
"""

from app.config import settings


def build_app_values(
    *,
    tenant_slug: str,
    app_slug: str,
    namespace: str,
    image: str,
    replicas: int,
    env_vars: dict[str, str],
    service_secret_names: list[str],
    port: int = 8000,
    custom_domain: str = "",
    health_check_path: str = "",
    resource_cpu_request: str = "50m",
    resource_cpu_limit: str = "500m",
    resource_memory_request: str = "64Mi",
    resource_memory_limit: str = "512Mi",
    min_replicas: int = 1,
    max_replicas: int = 5,
    cpu_threshold: int = 70,
    preset: str = "nonProd",
) -> dict:
    """Build haven-app Helm chart values for a tenant application."""
    image_repo, image_tag = image.rsplit(":", 1) if ":" in image else (image, "latest")

    values: dict = {
        "appSlug": app_slug,
        "tenantSlug": tenant_slug,
        "port": port,
        "replicas": replicas,
        "preset": preset,
        "image": {
            "repository": image_repo,
            "tag": image_tag,
            "pullPolicy": "Always",
            "pullSecrets": [{"name": settings.harbor_registry_secret}],
        },
        "env": env_vars,
        "envSecrets": service_secret_names,
        "resources": {
            "requests": {"cpu": resource_cpu_request, "memory": resource_memory_request},
            "limits": {"cpu": resource_cpu_limit, "memory": resource_memory_limit},
        },
        "autoscaling": {
            "enabled": True,
            "minReplicas": min_replicas,
            "maxReplicas": max_replicas,
            "targetCPUUtilizationPercentage": cpu_threshold,
        },
        "httproute": {
            "enabled": True,
            "gateway": {"name": "haven-gateway", "namespace": "haven-gateway"},
            "hostname": f"{app_slug}.{tenant_slug}.apps.{settings.lb_ip}.sslip.io",
        },
        "tolerations": [{"operator": "Exists"}],
    }

    if custom_domain:
        values["httproute"]["customDomain"] = custom_domain

    if health_check_path:
        values["probes"] = {
            "liveness": {"enabled": True, "type": "http", "path": health_check_path},
            "readiness": {"enabled": True, "type": "http", "path": health_check_path},
        }

    return values


def build_service_values(
    *,
    service_type: str,
    name: str,
    namespace: str,
    tier: str = "dev",
) -> dict:
    """Build haven-managed-service Helm chart values."""
    return {
        "serviceType": service_type,
        "name": name,
        "namespace": namespace,
        "tier": tier,
    }
