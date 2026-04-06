"""Tests for pod readiness check improvements in DeployService.wait_for_ready().

Covers:
  - Terminated container with non-zero exit code detection
  - Init container failure detection (CrashLoopBackOff, ErrImagePull)
  - Init container terminated with non-zero exit code
  - Successful readiness (ready_replicas >= 1)
  - Normal CrashLoopBackOff detection (existing behavior)
  - Timeout returns correct message
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.deploy_service import DeployService

# ---------------------------------------------------------------------------
# Helpers — build mock K8s objects
# ---------------------------------------------------------------------------


def _mock_k8s(*, deployment_status=None, pods=None):
    """Return a mock K8sClient with configurable deployment status and pod list."""
    k8s = MagicMock()
    k8s.is_available.return_value = True

    dep_obj = MagicMock()
    dep_obj.status = deployment_status or MagicMock()
    if deployment_status is None:
        dep_obj.status.ready_replicas = 0
    k8s.apps_v1 = MagicMock()
    k8s.apps_v1.read_namespaced_deployment_status.return_value = dep_obj

    pod_list = MagicMock()
    pod_list.items = pods or []
    k8s.core_v1 = MagicMock()
    k8s.core_v1.list_namespaced_pod.return_value = pod_list

    return k8s


def _make_pod(
    name: str = "test-pod-abc",
    container_statuses=None,
    init_container_statuses=None,
):
    """Build a mock Pod object."""
    pod = MagicMock()
    pod.metadata.name = name
    pod.status.container_statuses = container_statuses
    pod.status.init_container_statuses = init_container_statuses
    return pod


def _waiting_status(name: str = "app", reason: str = "CrashLoopBackOff", message: str = ""):
    """Build a container status in waiting state."""
    cs = MagicMock()
    cs.name = name
    cs.state.waiting.reason = reason
    cs.state.waiting.message = message
    cs.state.terminated = None
    return cs


def _terminated_status(name: str = "app", exit_code: int = 1, reason: str = "Error", message: str = ""):
    """Build a container status in terminated state."""
    cs = MagicMock()
    cs.name = name
    cs.state.waiting = None
    cs.state.terminated.exit_code = exit_code
    cs.state.terminated.reason = reason
    cs.state.terminated.message = message
    return cs


def _running_status(name: str = "app"):
    """Build a container status in running state (no waiting, no terminated)."""
    cs = MagicMock()
    cs.name = name
    cs.state.waiting = None
    cs.state.terminated = None
    return cs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPodReadinessFix:
    """Tests for DeployService.wait_for_ready()."""

    @pytest.mark.asyncio
    async def test_ready_replicas_returns_success(self):
        """When ready_replicas >= 1, wait_for_ready returns (True, 'Deployment ready')."""
        dep_status = MagicMock()
        dep_status.ready_replicas = 1
        k8s = _mock_k8s(deployment_status=dep_status)

        svc = DeployService(k8s)
        with patch("app.services.deploy_service.asyncio.sleep"):
            success, msg = await svc.wait_for_ready("tenant-test", "my-app", timeout=10)

        assert success is True
        assert msg == "Deployment ready"

    @pytest.mark.asyncio
    async def test_container_crashloopbackoff_detected(self):
        """CrashLoopBackOff on a regular container should be detected and return failure."""
        pod = _make_pod(
            container_statuses=[_waiting_status("app", "CrashLoopBackOff", "back-off 10s")],
        )
        k8s = _mock_k8s(pods=[pod])

        svc = DeployService(k8s)
        with patch("app.services.deploy_service.asyncio.sleep"):
            success, msg = await svc.wait_for_ready("tenant-test", "my-app", timeout=10)

        assert success is False
        assert "CrashLoopBackOff" in msg
        assert "test-pod-abc" in msg

    @pytest.mark.asyncio
    async def test_container_imagepullbackoff_detected(self):
        """ImagePullBackOff on a regular container should be detected."""
        pod = _make_pod(
            container_statuses=[_waiting_status("app", "ImagePullBackOff", "image not found")],
        )
        k8s = _mock_k8s(pods=[pod])

        svc = DeployService(k8s)
        with patch("app.services.deploy_service.asyncio.sleep"):
            success, msg = await svc.wait_for_ready("tenant-test", "my-app", timeout=10)

        assert success is False
        assert "ImagePullBackOff" in msg

    @pytest.mark.asyncio
    async def test_container_terminated_nonzero_exit_detected(self):
        """Terminated container with non-zero exit code should be detected."""
        pod = _make_pod(
            container_statuses=[_terminated_status("app", exit_code=137, reason="OOMKilled", message="oom")],
        )
        k8s = _mock_k8s(pods=[pod])

        svc = DeployService(k8s)
        with patch("app.services.deploy_service.asyncio.sleep"):
            success, msg = await svc.wait_for_ready("tenant-test", "my-app", timeout=10)

        assert success is False
        assert "terminated" in msg.lower() or "exit code" in msg.lower()
        assert "137" in msg
        assert "OOMKilled" in msg

    @pytest.mark.asyncio
    async def test_init_container_crashloopbackoff_detected(self):
        """CrashLoopBackOff on an init container should be detected."""
        pod = _make_pod(
            container_statuses=[_running_status("app")],
            init_container_statuses=[_waiting_status("init-db", "CrashLoopBackOff", "back-off")],
        )
        k8s = _mock_k8s(pods=[pod])

        svc = DeployService(k8s)
        with patch("app.services.deploy_service.asyncio.sleep"):
            success, msg = await svc.wait_for_ready("tenant-test", "my-app", timeout=10)

        assert success is False
        assert "init container" in msg.lower()
        assert "CrashLoopBackOff" in msg

    @pytest.mark.asyncio
    async def test_init_container_errimagepull_detected(self):
        """ErrImagePull on an init container should be detected."""
        pod = _make_pod(
            container_statuses=[_running_status("app")],
            init_container_statuses=[_waiting_status("init-setup", "ErrImagePull", "pull failed")],
        )
        k8s = _mock_k8s(pods=[pod])

        svc = DeployService(k8s)
        with patch("app.services.deploy_service.asyncio.sleep"):
            success, msg = await svc.wait_for_ready("tenant-test", "my-app", timeout=10)

        assert success is False
        assert "init container" in msg.lower()
        assert "ErrImagePull" in msg

    @pytest.mark.asyncio
    async def test_init_container_terminated_nonzero_exit_detected(self):
        """Init container terminated with non-zero exit code should be detected."""
        pod = _make_pod(
            container_statuses=[_running_status("app")],
            init_container_statuses=[_terminated_status("init-migrate", exit_code=2, reason="Error")],
        )
        k8s = _mock_k8s(pods=[pod])

        svc = DeployService(k8s)
        with patch("app.services.deploy_service.asyncio.sleep"):
            success, msg = await svc.wait_for_ready("tenant-test", "my-app", timeout=10)

        assert success is False
        assert "init container" in msg.lower()
        assert "exit code" in msg.lower()
        assert "2" in msg

    @pytest.mark.asyncio
    async def test_timeout_returns_correct_message(self):
        """When no pods report errors but deployment never becomes ready, timeout message is returned."""
        # Pods exist but no errors and no ready replicas
        pod = _make_pod(
            container_statuses=[_running_status("app")],
        )
        k8s = _mock_k8s(pods=[pod])

        svc = DeployService(k8s)
        with patch("app.services.deploy_service.asyncio.sleep"):
            success, msg = await svc.wait_for_ready("tenant-test", "my-app", timeout=10)

        assert success is False
        assert "not ready after" in msg.lower()
        assert "10s" in msg

    @pytest.mark.asyncio
    async def test_container_terminated_zero_exit_not_flagged(self):
        """Terminated container with exit code 0 should NOT be treated as failure."""
        # Exit code 0 = success (e.g. completed init container), should not fail
        pod = _make_pod(
            container_statuses=[_terminated_status("app", exit_code=0, reason="Completed")],
        )
        k8s = _mock_k8s(pods=[pod])

        svc = DeployService(k8s)
        with patch("app.services.deploy_service.asyncio.sleep"):
            success, msg = await svc.wait_for_ready("tenant-test", "my-app", timeout=10)

        # Should timeout, not fail early — exit code 0 is not an error
        assert success is False
        assert "not ready after" in msg.lower()
