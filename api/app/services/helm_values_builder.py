"""Builds Helm values dicts for tenant apps and managed services.

Used by the GitOps service to generate values.yaml content that
the ArgoCD ApplicationSet picks up and syncs to the cluster.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from app.models.application import Application


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


def render_app_values(app: Application, tenant_slug: str) -> dict:
    """Build Helm values dict from an Application model's current state.

    Derives service secret names from app.env_from_secrets.
    Namespace is derived as tenant-{tenant_slug}.
    """
    secret_names = [
        e.get("secret_name", "")
        for e in (app.env_from_secrets or [])
        if e.get("secret_name")
    ]
    return build_app_values(
        tenant_slug=tenant_slug,
        app_slug=app.slug,
        namespace=f"tenant-{tenant_slug}",
        image=app.image_tag or "",
        replicas=app.replicas,
        env_vars=dict(app.env_vars or {}),
        service_secret_names=secret_names,
        port=app.port,
        custom_domain=app.custom_domain or "",
        health_check_path=app.health_check_path or "",
        resource_cpu_request=app.resource_cpu_request,
        resource_cpu_limit=app.resource_cpu_limit,
        resource_memory_request=app.resource_memory_request,
        resource_memory_limit=app.resource_memory_limit,
        min_replicas=app.min_replicas,
        max_replicas=app.max_replicas,
        cpu_threshold=app.cpu_threshold,
    )


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
