"""Tests for deploy_service.py — verifying that all app fields are used correctly.

Covers Batch 1A fixes:
  - Resource limits (cpu/memory request/limit) passed to K8s Deployment
  - Health check path (HTTP probe when configured, TCP when not)
  - Custom domain added to HTTPRoute hostnames
  - HPA min/max replicas and CPU threshold from app config
  - app_type=worker skips Service/HTTPRoute/HPA
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.exceptions import ApiException

from app.services.deploy_service import DeployService


@pytest.fixture
def k8s_mock():
    """Create a mocked K8sClient with all required APIs."""
    k8s = MagicMock()
    k8s.is_available.return_value = True
    k8s.apps_v1 = MagicMock()
    k8s.core_v1 = MagicMock()
    k8s.autoscaling_v2 = MagicMock()
    k8s.custom_objects = MagicMock()

    # Make read raise 404 so create is called (new resources)
    not_found = ApiException(status=404, reason="Not Found")
    k8s.apps_v1.read_namespaced_deployment.side_effect = not_found
    k8s.apps_v1.create_namespaced_deployment.return_value = None
    k8s.core_v1.read_namespaced_service.side_effect = not_found
    k8s.core_v1.create_namespaced_service.return_value = None
    k8s.autoscaling_v2.read_namespaced_horizontal_pod_autoscaler.side_effect = not_found
    k8s.autoscaling_v2.create_namespaced_horizontal_pod_autoscaler.return_value = None
    k8s.custom_objects.get_namespaced_custom_object.side_effect = not_found
    k8s.custom_objects.create_namespaced_custom_object.return_value = None
    return k8s


@pytest.fixture
def deploy_svc(k8s_mock):
    return DeployService(k8s_mock)


def _get_created_deployment(k8s_mock):
    """Extract the Deployment body from the create call."""
    call_args = k8s_mock.apps_v1.create_namespaced_deployment.call_args
    return call_args[1]["body"] if call_args[1] else call_args[0][1]


def _get_created_hpa(k8s_mock):
    """Extract the HPA body from the create call."""
    call_args = k8s_mock.autoscaling_v2.create_namespaced_horizontal_pod_autoscaler.call_args
    return call_args[1]["body"] if call_args[1] else call_args[0][1]


def _get_created_httproute(k8s_mock):
    """Extract the HTTPRoute body from the create call."""
    call_args = k8s_mock.custom_objects.create_namespaced_custom_object.call_args
    return call_args[1]["body"] if call_args[1] else call_args[0][-1]


# ---------------------------------------------------------------------------
# Resource Limits Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_uses_custom_resource_limits(deploy_svc, k8s_mock):
    """Resources from app config must reach K8s Deployment, not hardcoded defaults."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=2,
        env_vars={},
        port=8080,
        resource_cpu_request="200m",
        resource_cpu_limit="1000m",
        resource_memory_request="256Mi",
        resource_memory_limit="1Gi",
    )

    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    assert container.resources.requests["cpu"] == "200m"
    assert container.resources.requests["memory"] == "256Mi"
    assert container.resources.limits["cpu"] == "1000m"
    assert container.resources.limits["memory"] == "1Gi"


@pytest.mark.asyncio
async def test_deploy_default_resource_limits(deploy_svc, k8s_mock):
    """Default resource values when not specified."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
    )

    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    assert container.resources.requests["cpu"] == "50m"
    assert container.resources.requests["memory"] == "64Mi"
    assert container.resources.limits["cpu"] == "500m"
    assert container.resources.limits["memory"] == "512Mi"


@pytest.mark.asyncio
async def test_deploy_starter_tier_resources(deploy_svc, k8s_mock):
    """Starter tier resources (100m/200m CPU, 128Mi/256Mi RAM)."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
        resource_cpu_request="100m",
        resource_cpu_limit="200m",
        resource_memory_request="128Mi",
        resource_memory_limit="256Mi",
    )

    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    assert container.resources.requests["cpu"] == "100m"
    assert container.resources.limits["cpu"] == "200m"
    assert container.resources.requests["memory"] == "128Mi"
    assert container.resources.limits["memory"] == "256Mi"


@pytest.mark.asyncio
async def test_deploy_performance_tier_resources(deploy_svc, k8s_mock):
    """Performance tier resources (1000m/2000m CPU, 1Gi/2Gi RAM)."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
        resource_cpu_request="1000m",
        resource_cpu_limit="2000m",
        resource_memory_request="1Gi",
        resource_memory_limit="2Gi",
    )

    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    assert container.resources.requests["cpu"] == "1000m"
    assert container.resources.limits["cpu"] == "2000m"
    assert container.resources.requests["memory"] == "1Gi"
    assert container.resources.limits["memory"] == "2Gi"


# ---------------------------------------------------------------------------
# Health Check Path Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_tcp_probe_when_no_health_path(deploy_svc, k8s_mock):
    """Without health_check_path, use TCP liveness probe."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
        health_check_path="",
    )

    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    assert container.liveness_probe.tcp_socket is not None
    assert container.liveness_probe.http_get is None
    assert container.readiness_probe is None  # No readiness without health path


@pytest.mark.asyncio
async def test_deploy_http_probe_when_health_path_set(deploy_svc, k8s_mock):
    """With health_check_path, use HTTP liveness and readiness probes."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
        port=8080,
        health_check_path="/health",
    )

    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    # Liveness probe should be HTTP
    assert container.liveness_probe.http_get is not None
    assert container.liveness_probe.http_get.path == "/health"
    assert container.liveness_probe.http_get.port == 8080
    assert container.liveness_probe.tcp_socket is None
    # Readiness probe should also be HTTP
    assert container.readiness_probe is not None
    assert container.readiness_probe.http_get.path == "/health"
    assert container.readiness_probe.http_get.port == 8080


@pytest.mark.asyncio
async def test_deploy_http_probe_custom_path(deploy_svc, k8s_mock):
    """Health check path can be any custom path."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
        health_check_path="/api/v1/healthz",
    )

    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    assert container.liveness_probe.http_get.path == "/api/v1/healthz"


# ---------------------------------------------------------------------------
# Custom Domain Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_httproute_default_hostname(deploy_svc, k8s_mock):
    """Without custom_domain, HTTPRoute has only sslip.io hostname."""
    with patch("app.services.deploy_service.settings") as mock_settings:
        mock_settings.lb_ip = "1.2.3.4"
        mock_settings.harbor_registry_secret = "harbor-robot-secret"
        await deploy_svc.deploy(
            namespace="tenant-test",
            tenant_slug="test",
            app_slug="myapp",
            image="harbor/test/myapp:abc",
            replicas=1,
            env_vars={},
            custom_domain="",
        )

    route = _get_created_httproute(k8s_mock)
    assert route["spec"]["hostnames"] == ["myapp.test.apps.1.2.3.4.sslip.io"]


@pytest.mark.asyncio
async def test_deploy_httproute_with_custom_domain(deploy_svc, k8s_mock):
    """With custom_domain, HTTPRoute includes both hostnames."""
    with patch("app.services.deploy_service.settings") as mock_settings:
        mock_settings.lb_ip = "1.2.3.4"
        mock_settings.harbor_registry_secret = "harbor-robot-secret"
        await deploy_svc.deploy(
            namespace="tenant-test",
            tenant_slug="test",
            app_slug="myapp",
            image="harbor/test/myapp:abc",
            replicas=1,
            env_vars={},
            custom_domain="api.example.nl",
        )

    route = _get_created_httproute(k8s_mock)
    hostnames = route["spec"]["hostnames"]
    assert "myapp.test.apps.1.2.3.4.sslip.io" in hostnames
    assert "api.example.nl" in hostnames
    assert len(hostnames) == 2


# ---------------------------------------------------------------------------
# HPA Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_hpa_uses_custom_values(deploy_svc, k8s_mock):
    """HPA min/max/cpu_threshold from app config, not hardcoded."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=2,
        env_vars={},
        min_replicas=2,
        max_replicas=10,
        cpu_threshold=80,
    )

    hpa = _get_created_hpa(k8s_mock)
    assert hpa.spec.min_replicas == 2
    assert hpa.spec.max_replicas == 10
    assert hpa.spec.metrics[0].resource.target.average_utilization == 80


@pytest.mark.asyncio
async def test_deploy_hpa_default_values(deploy_svc, k8s_mock):
    """Default HPA values when not specified."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
    )

    hpa = _get_created_hpa(k8s_mock)
    assert hpa.spec.min_replicas == 1
    assert hpa.spec.max_replicas == 5
    assert hpa.spec.metrics[0].resource.target.average_utilization == 70


@pytest.mark.asyncio
async def test_deploy_hpa_aggressive_scaling(deploy_svc, k8s_mock):
    """Aggressive scaling: low threshold, high max replicas."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=3,
        env_vars={},
        min_replicas=3,
        max_replicas=20,
        cpu_threshold=50,
    )

    hpa = _get_created_hpa(k8s_mock)
    assert hpa.spec.min_replicas == 3
    assert hpa.spec.max_replicas == 20
    assert hpa.spec.metrics[0].resource.target.average_utilization == 50


# ---------------------------------------------------------------------------
# app_type=worker Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_worker_skips_service(deploy_svc, k8s_mock):
    """Workers should NOT create K8s Service."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myworker",
        image="harbor/test/myworker:abc",
        replicas=1,
        env_vars={},
        app_type="worker",
    )

    # Deployment should still be created
    k8s_mock.apps_v1.create_namespaced_deployment.assert_called_once()
    # Service should NOT be created
    k8s_mock.core_v1.create_namespaced_service.assert_not_called()


@pytest.mark.asyncio
async def test_deploy_worker_skips_httproute(deploy_svc, k8s_mock):
    """Workers should NOT create HTTPRoute."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myworker",
        image="harbor/test/myworker:abc",
        replicas=1,
        env_vars={},
        app_type="worker",
    )

    # HTTPRoute should NOT be created
    k8s_mock.custom_objects.create_namespaced_custom_object.assert_not_called()


@pytest.mark.asyncio
async def test_deploy_worker_skips_hpa(deploy_svc, k8s_mock):
    """Workers should NOT create HPA."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myworker",
        image="harbor/test/myworker:abc",
        replicas=1,
        env_vars={},
        app_type="worker",
    )

    # HPA should NOT be created
    k8s_mock.autoscaling_v2.create_namespaced_horizontal_pod_autoscaler.assert_not_called()


@pytest.mark.asyncio
async def test_deploy_worker_still_creates_deployment(deploy_svc, k8s_mock):
    """Workers still need a Deployment resource."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myworker",
        image="harbor/test/myworker:abc",
        replicas=2,
        env_vars={"QUEUE_URL": "redis://localhost"},
        app_type="worker",
    )

    dep = _get_created_deployment(k8s_mock)
    assert dep.spec.replicas == 2
    container = dep.spec.template.spec.containers[0]
    assert container.image == "harbor/test/myworker:abc"


@pytest.mark.asyncio
async def test_deploy_web_creates_all_resources(deploy_svc, k8s_mock):
    """Web type creates Deployment + Service + HTTPRoute + HPA."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
        app_type="web",
    )

    k8s_mock.apps_v1.create_namespaced_deployment.assert_called_once()
    k8s_mock.core_v1.create_namespaced_service.assert_called_once()
    k8s_mock.custom_objects.create_namespaced_custom_object.assert_called_once()
    k8s_mock.autoscaling_v2.create_namespaced_horizontal_pod_autoscaler.assert_called_once()


@pytest.mark.asyncio
async def test_deploy_default_type_is_web(deploy_svc, k8s_mock):
    """Default app_type should be 'web' — creates all resources."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
    )

    k8s_mock.apps_v1.create_namespaced_deployment.assert_called_once()
    k8s_mock.core_v1.create_namespaced_service.assert_called_once()


# ---------------------------------------------------------------------------
# K8s unavailable guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_noop_when_k8s_unavailable(k8s_mock):
    """Deploy should be a no-op when K8s is unavailable."""
    k8s_mock.is_available.return_value = False
    deploy_svc = DeployService(k8s_mock)

    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
    )

    k8s_mock.apps_v1.create_namespaced_deployment.assert_not_called()


# ---------------------------------------------------------------------------
# Port and env var injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_injects_port_env_var(deploy_svc, k8s_mock):
    """PORT env var should match the configured port."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={"FOO": "bar"},
        port=3000,
    )

    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    env_dict = {e.name: e.value for e in container.env}
    assert env_dict["PORT"] == "3000"
    assert env_dict["FOO"] == "bar"
    assert container.ports[0].container_port == 3000


@pytest.mark.asyncio
async def test_deploy_injects_service_secrets(deploy_svc, k8s_mock):
    """Service secret names should be injected as envFrom secretRef."""
    await deploy_svc.deploy(
        namespace="tenant-test",
        tenant_slug="test",
        app_slug="myapp",
        image="harbor/test/myapp:abc",
        replicas=1,
        env_vars={},
        service_secret_names=["svc-mydb", "svc-myredis"],
    )

    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    secret_names = [ef.secret_ref.name for ef in container.env_from]
    assert "svc-mydb" in secret_names
    assert "svc-myredis" in secret_names


# ---------------------------------------------------------------------------
# Combined scenario tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_full_config_web_app(deploy_svc, k8s_mock):
    """Full config: custom resources, health check, custom domain, HPA."""
    with patch("app.services.deploy_service.settings") as mock_settings:
        mock_settings.lb_ip = "10.0.0.1"
        mock_settings.harbor_registry_secret = "harbor-robot-secret"
        await deploy_svc.deploy(
            namespace="tenant-demo",
            tenant_slug="demo",
            app_slug="backend-api",
            image="harbor/demo/backend-api:abc123",
            replicas=3,
            env_vars={"DATABASE_URL": "postgres://...", "REDIS_URL": "redis://..."},
            service_secret_names=["svc-backend-pg"],
            port=8080,
            resource_cpu_request="500m",
            resource_cpu_limit="2000m",
            resource_memory_request="512Mi",
            resource_memory_limit="2Gi",
            health_check_path="/api/health",
            custom_domain="api.gemeente-demo.nl",
            min_replicas=2,
            max_replicas=10,
            cpu_threshold=60,
            app_type="web",
        )

    # Verify Deployment
    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    assert container.resources.requests["cpu"] == "500m"
    assert container.resources.limits["memory"] == "2Gi"
    assert container.liveness_probe.http_get.path == "/api/health"
    assert container.liveness_probe.http_get.port == 8080
    assert container.readiness_probe.http_get.path == "/api/health"

    # Verify HPA
    hpa = _get_created_hpa(k8s_mock)
    assert hpa.spec.min_replicas == 2
    assert hpa.spec.max_replicas == 10

    # Verify HTTPRoute
    route = _get_created_httproute(k8s_mock)
    assert "api.gemeente-demo.nl" in route["spec"]["hostnames"]


@pytest.mark.asyncio
async def test_deploy_full_config_worker_app(deploy_svc, k8s_mock):
    """Full config worker: custom resources, no ingress resources."""
    await deploy_svc.deploy(
        namespace="tenant-demo",
        tenant_slug="demo",
        app_slug="queue-worker",
        image="harbor/demo/queue-worker:abc123",
        replicas=5,
        env_vars={"QUEUE_URL": "amqp://..."},
        port=8080,
        resource_cpu_request="200m",
        resource_cpu_limit="1000m",
        resource_memory_request="256Mi",
        resource_memory_limit="1Gi",
        app_type="worker",
    )

    # Deployment created with correct resources
    dep = _get_created_deployment(k8s_mock)
    container = dep.spec.template.spec.containers[0]
    assert container.resources.requests["cpu"] == "200m"
    assert dep.spec.replicas == 5

    # No Service, HTTPRoute, or HPA
    k8s_mock.core_v1.create_namespaced_service.assert_not_called()
    k8s_mock.custom_objects.create_namespaced_custom_object.assert_not_called()
    k8s_mock.autoscaling_v2.create_namespaced_horizontal_pod_autoscaler.assert_not_called()
