"""Tests for webhook auto_deploy check and build_service use_dockerfile guard.

Covers Batch 1B + 1C fixes:
  - auto_deploy=False should block webhook-triggered builds
  - use_dockerfile=True should skip Nixpacks and fail if no Dockerfile found
  - use_dockerfile=False should use Nixpacks (existing behavior)
"""

from __future__ import annotations

import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.build_service import BuildService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(**kwargs) -> types.SimpleNamespace:
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "slug": "my-app",
        "name": "My App",
        "repo_url": "https://github.com/org/repo",
        "branch": "main",
        "env_vars": {},
        "image_tag": None,
        "replicas": 1,
        "port": 8000,
        "env_from_secrets": None,
        "custom_domain": None,
        "health_check_path": None,
        "resource_cpu_request": "50m",
        "resource_cpu_limit": "500m",
        "resource_memory_request": "64Mi",
        "resource_memory_limit": "512Mi",
        "min_replicas": 1,
        "max_replicas": 5,
        "cpu_threshold": 70,
        "webhook_token": "test-token-123",
        "auto_deploy": True,
        "dockerfile_path": None,
        "build_context": None,
        "use_dockerfile": False,
        "app_type": "web",
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _make_tenant(**kwargs) -> types.SimpleNamespace:
    defaults = {
        "id": uuid.uuid4(),
        "slug": "test-tenant",
        "namespace": "tenant-test-tenant",
        "github_token": None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# auto_deploy Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_ignored_when_auto_deploy_disabled():
    """Push webhook should be ignored when auto_deploy=False."""
    from app.routers.webhooks import _handle_push

    app = _make_app(auto_deploy=False)
    tenant = _make_tenant()

    # Mock DB to return the app
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = app
    mock_db.execute.return_value = mock_result
    mock_db.get.return_value = tenant

    # Mock request with push payload
    mock_request = MagicMock()
    mock_request.json = AsyncMock(
        return_value={
            "ref": "refs/heads/main",
            "after": "abc1234567890",
        }
    )

    result = await _handle_push("test-token-123", mock_request, mock_db, MagicMock(), MagicMock(), MagicMock())

    assert result["status"] == "ignored"
    assert result["reason"] == "auto_deploy disabled"


@pytest.mark.asyncio
async def test_webhook_proceeds_when_auto_deploy_enabled():
    """Push webhook should proceed when auto_deploy=True (existing behavior)."""
    from app.routers.webhooks import _handle_push

    app = _make_app(auto_deploy=True)
    tenant = _make_tenant()

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = app
    mock_db.execute.return_value = mock_result
    mock_db.get.return_value = tenant
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    mock_request = MagicMock()
    mock_request.json = AsyncMock(
        return_value={
            "ref": "refs/heads/main",
            "after": "abc1234567890",
        }
    )

    with patch("app.routers.webhooks.run_pipeline", new_callable=AsyncMock):
        with patch("app.routers.webhooks.get_session_factory"):
            with patch("app.routers.webhooks.Deployment") as mock_dep:
                mock_dep.return_value = MagicMock(id=uuid.uuid4())
                result = await _handle_push(
                    "test-token-123", mock_request, mock_db, MagicMock(), MagicMock(), MagicMock()
                )

    assert result["status"] == "queued"


@pytest.mark.asyncio
async def test_webhook_branch_mismatch_still_checked_before_auto_deploy():
    """Branch mismatch should be checked before auto_deploy."""
    from app.routers.webhooks import _handle_push

    app = _make_app(auto_deploy=False, branch="main")

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = app
    mock_db.execute.return_value = mock_result

    mock_request = MagicMock()
    mock_request.json = AsyncMock(
        return_value={
            "ref": "refs/heads/develop",
            "after": "abc1234567890",
        }
    )

    result = await _handle_push("test-token-123", mock_request, mock_db, MagicMock(), MagicMock(), MagicMock())
    assert result["reason"] == "branch mismatch"


# ---------------------------------------------------------------------------
# use_dockerfile Tests (build_service)
# ---------------------------------------------------------------------------


def test_build_job_use_dockerfile_true_generates_strict_check():
    """When use_dockerfile=True, nixpacks init container should fail if no Dockerfile."""
    k8s_mock = MagicMock()
    build_svc = BuildService(k8s_mock)

    job = build_svc._build_job_manifest(
        job_name="build-test-abc123-xyz",
        namespace="haven-builds",
        app_slug="myapp",
        repo_url="https://github.com/org/repo",
        branch="main",
        commit_sha="abc1234567890",
        image_name="harbor/test/myapp:abc",
        use_dockerfile=True,
    )

    # Find the nixpacks init container
    nixpacks_container = None
    for ic in job.spec.template.spec.init_containers:
        if ic.name == "nixpacks":
            nixpacks_container = ic
            break

    assert nixpacks_container is not None
    nixpacks_cmd = nixpacks_container.args[0]

    # Should NOT contain nixpacks download
    assert "NIXPACKS_VERSION" not in nixpacks_cmd
    # Should contain error message for missing Dockerfile
    assert "use_dockerfile is enabled" in nixpacks_cmd
    assert "exit 1" in nixpacks_cmd


def test_build_job_use_dockerfile_false_runs_nixpacks():
    """When use_dockerfile=False, nixpacks init container downloads and runs nixpacks."""
    k8s_mock = MagicMock()
    build_svc = BuildService(k8s_mock)

    job = build_svc._build_job_manifest(
        job_name="build-test-abc123-xyz",
        namespace="haven-builds",
        app_slug="myapp",
        repo_url="https://github.com/org/repo",
        branch="main",
        commit_sha="abc1234567890",
        image_name="harbor/test/myapp:abc",
        use_dockerfile=False,
    )

    nixpacks_container = None
    for ic in job.spec.template.spec.init_containers:
        if ic.name == "nixpacks":
            nixpacks_container = ic
            break

    assert nixpacks_container is not None
    nixpacks_cmd = nixpacks_container.args[0]

    # Should contain nixpacks download
    assert "NIXPACKS_VERSION" in nixpacks_cmd
    # Should NOT contain strict error
    assert "use_dockerfile is enabled" not in nixpacks_cmd


def test_build_job_use_dockerfile_with_custom_path():
    """use_dockerfile=True with dockerfile_path should check that specific path."""
    k8s_mock = MagicMock()
    build_svc = BuildService(k8s_mock)

    job = build_svc._build_job_manifest(
        job_name="build-test-abc123-xyz",
        namespace="haven-builds",
        app_slug="myapp",
        repo_url="https://github.com/org/repo",
        branch="main",
        commit_sha="abc1234567890",
        image_name="harbor/test/myapp:abc",
        dockerfile_path="backend/Dockerfile",
        use_dockerfile=True,
    )

    nixpacks_container = None
    for ic in job.spec.template.spec.init_containers:
        if ic.name == "nixpacks":
            nixpacks_container = ic
            break

    nixpacks_cmd = nixpacks_container.args[0]
    assert "/workspace/backend/Dockerfile" in nixpacks_cmd


def test_build_job_use_dockerfile_with_build_context():
    """use_dockerfile=True with build_context should copy Dockerfile to context dir."""
    k8s_mock = MagicMock()
    build_svc = BuildService(k8s_mock)

    job = build_svc._build_job_manifest(
        job_name="build-test-abc123-xyz",
        namespace="haven-builds",
        app_slug="myapp",
        repo_url="https://github.com/org/repo",
        branch="main",
        commit_sha="abc1234567890",
        image_name="harbor/test/myapp:abc",
        dockerfile_path="backend/Dockerfile.prod",
        build_context="backend",
        use_dockerfile=True,
    )

    nixpacks_container = None
    for ic in job.spec.template.spec.init_containers:
        if ic.name == "nixpacks":
            nixpacks_container = ic
            break

    nixpacks_cmd = nixpacks_container.args[0]
    assert "/workspace/backend/Dockerfile.prod" in nixpacks_cmd
    assert "/workspace/backend/Dockerfile" in nixpacks_cmd  # copy target


def test_build_job_default_use_dockerfile_is_false():
    """Default use_dockerfile should be False (Nixpacks mode)."""
    k8s_mock = MagicMock()
    build_svc = BuildService(k8s_mock)

    job = build_svc._build_job_manifest(
        job_name="build-test-abc123-xyz",
        namespace="haven-builds",
        app_slug="myapp",
        repo_url="https://github.com/org/repo",
        branch="main",
        commit_sha="abc1234567890",
        image_name="harbor/test/myapp:abc",
    )

    nixpacks_container = None
    for ic in job.spec.template.spec.init_containers:
        if ic.name == "nixpacks":
            nixpacks_container = ic
            break

    nixpacks_cmd = nixpacks_container.args[0]
    assert "NIXPACKS_VERSION" in nixpacks_cmd


# ---------------------------------------------------------------------------
# Pipeline passes use_dockerfile
# ---------------------------------------------------------------------------


def test_pipeline_run_pipeline_signature_includes_use_dockerfile():
    """run_pipeline must accept use_dockerfile parameter."""
    import inspect

    from app.services.pipeline import run_pipeline

    sig = inspect.signature(run_pipeline)
    assert "use_dockerfile" in sig.parameters
    assert sig.parameters["use_dockerfile"].default is False


def test_build_service_trigger_build_signature_includes_use_dockerfile():
    """trigger_build must accept use_dockerfile parameter."""
    import inspect

    sig = inspect.signature(BuildService.trigger_build)
    assert "use_dockerfile" in sig.parameters
    assert sig.parameters["use_dockerfile"].default is False


# ---------------------------------------------------------------------------
# Pipeline passes extended params to direct deploy
# ---------------------------------------------------------------------------


def test_pipeline_direct_deploy_passes_all_params():
    """Verify pipeline direct K8s mode passes extended params to deploy()."""
    import inspect

    from app.services.deploy_service import DeployService

    sig = inspect.signature(DeployService.deploy)
    expected_params = [
        "resource_cpu_request",
        "resource_cpu_limit",
        "resource_memory_request",
        "resource_memory_limit",
        "health_check_path",
        "custom_domain",
        "min_replicas",
        "max_replicas",
        "cpu_threshold",
        "app_type",
    ]
    for param in expected_params:
        assert param in sig.parameters, f"DeployService.deploy missing param: {param}"
