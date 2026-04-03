"""Tests for Sprint E7: GitOps flow verification.

Tests: Gitea scaffold, values.yaml builder, ArgoCD AppSet, helm chart.
"""

from unittest.mock import MagicMock

from app.models.application import Application
from app.services.helm_values_builder import build_app_values, render_app_values

# ---------------------------------------------------------------------------
# Helm values builder tests
# ---------------------------------------------------------------------------


def test_build_app_values_basic():
    """build_app_values generates correct structure."""
    values = build_app_values(
        tenant_slug="rotterdam",
        app_slug="rotterdam-api",
        namespace="tenant-rotterdam",
        image="harbor.io/haven/tenant-rotterdam/rotterdam-api:abc123",
        replicas=2,
        env_vars={"DEBUG": "true"},
        service_secret_names=["svc-app-pg", "svc-app-redis"],
        port=8080,
    )
    assert values["appSlug"] == "rotterdam-api"
    assert values["tenantSlug"] == "rotterdam"
    assert values["port"] == 8080
    assert values["replicas"] == 2
    assert values["image"]["tag"] == "abc123"
    assert "harbor.io/haven/tenant-rotterdam/rotterdam-api" in values["image"]["repository"]
    assert values["env"]["DEBUG"] == "true"
    assert "svc-app-pg" in values["envSecrets"]
    assert "svc-app-redis" in values["envSecrets"]


def test_build_app_values_empty_env():
    """build_app_values with empty env_vars."""
    values = build_app_values(
        tenant_slug="test", app_slug="app", namespace="tenant-test",
        image="harbor.io/test:v1", replicas=1, env_vars={},
        service_secret_names=[], port=3000,
    )
    assert values["env"] == {}
    assert isinstance(values["envSecrets"], list)


def test_build_app_values_with_custom_domain():
    """build_app_values includes custom domain in httproute."""
    values = build_app_values(
        tenant_slug="test", app_slug="app", namespace="tenant-test",
        image="harbor.io/test:v1", replicas=1, env_vars={},
        service_secret_names=[], port=8080, custom_domain="api.rotterdam.nl",
    )
    assert values["httproute"]["customDomain"] == "api.rotterdam.nl"


def test_build_app_values_with_health_check():
    """build_app_values includes health check probes."""
    values = build_app_values(
        tenant_slug="test", app_slug="app", namespace="tenant-test",
        image="harbor.io/test:v1", replicas=1, env_vars={},
        service_secret_names=[], port=8080, health_check_path="/health",
    )
    assert values["probes"]["liveness"]["path"] == "/health"
    assert values["probes"]["readiness"]["path"] == "/health"


def test_build_app_values_autoscaling():
    """build_app_values includes HPA config."""
    values = build_app_values(
        tenant_slug="test", app_slug="app", namespace="tenant-test",
        image="harbor.io/test:v1", replicas=1, env_vars={},
        service_secret_names=[], port=8080,
        min_replicas=2, max_replicas=10, cpu_threshold=80,
    )
    assert values["autoscaling"]["enabled"] is True
    assert values["autoscaling"]["minReplicas"] == 2
    assert values["autoscaling"]["maxReplicas"] == 10
    assert values["autoscaling"]["targetCPUUtilizationPercentage"] == 80


def test_build_app_values_resources():
    """build_app_values includes resource requests/limits."""
    values = build_app_values(
        tenant_slug="test", app_slug="app", namespace="tenant-test",
        image="harbor.io/test:v1", replicas=1, env_vars={},
        service_secret_names=[], port=8080,
        resource_cpu_request="100m", resource_cpu_limit="1",
        resource_memory_request="128Mi", resource_memory_limit="1Gi",
    )
    assert values["resources"]["requests"]["cpu"] == "100m"
    assert values["resources"]["limits"]["memory"] == "1Gi"


def test_build_app_values_tolerations():
    """build_app_values includes CIS hardening tolerations."""
    values = build_app_values(
        tenant_slug="test", app_slug="app", namespace="tenant-test",
        image="harbor.io/test:v1", replicas=1, env_vars={},
        service_secret_names=[], port=8080,
    )
    assert values["tolerations"] == [{"operator": "Exists"}]


def test_render_app_values_derives_secrets():
    """render_app_values extracts secret names from env_from_secrets."""
    app_model = MagicMock(spec=Application)
    app_model.slug = "test-api"
    app_model.port = 8080
    app_model.replicas = 1
    app_model.env_vars = {}
    app_model.env_from_secrets = [
        {"secret_name": "svc-pg", "service_name": "pg"},
        {"secret_name": "svc-redis", "service_name": "redis"},
    ]
    app_model.image_tag = "harbor.io/test:v1"
    app_model.custom_domain = None
    app_model.health_check_path = None
    app_model.resource_cpu_request = "50m"
    app_model.resource_cpu_limit = "500m"
    app_model.resource_memory_request = "64Mi"
    app_model.resource_memory_limit = "512Mi"
    app_model.min_replicas = 1
    app_model.max_replicas = 5
    app_model.cpu_threshold = 70

    values = render_app_values(app_model, "test")
    assert "svc-pg" in values["envSecrets"]
    assert "svc-redis" in values["envSecrets"]
    assert "test-api-env-secrets" in values["envSecrets"]


# ---------------------------------------------------------------------------
# Gitea scaffold tests
# ---------------------------------------------------------------------------


def test_gitops_scaffold_module_exists():
    """gitops_scaffold module is importable with GitOpsScaffold."""
    from app.services.gitops_scaffold import GitOpsScaffold, gitops_scaffold

    assert gitops_scaffold is not None
    assert GitOpsScaffold is not None


def test_gitops_service_has_write_methods():
    """GitOpsService has write_app_values and delete methods."""
    from app.services.gitops_service import GitOpsService

    svc = GitOpsService()
    assert hasattr(svc, "write_app_values")
    assert hasattr(svc, "delete_tenant")
    assert hasattr(svc, "delete_app")


# ---------------------------------------------------------------------------
# ArgoCD service tests
# ---------------------------------------------------------------------------


def test_argocd_service_has_rollback():
    """ArgoCDService has rollback and sync methods."""
    from app.services.argocd_service import ArgoCDService

    svc = ArgoCDService()
    assert hasattr(svc, "rollback_app")
    assert hasattr(svc, "trigger_sync")
    assert hasattr(svc, "get_app_status")
    assert hasattr(svc, "get_app_history")
