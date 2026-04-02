"""Tests for Sprint I-5: API → GitOps integration.

Covers:
  - render_app_values: builds correct Helm values from Application model
  - PATCH /apps/{slug}: enqueues UPDATE_FILE on config change
  - connect/disconnect service: enqueues UPDATE_FILE on envFrom change
  - pipeline: enqueues image tag update after RUNNING
"""

from __future__ import annotations

import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.git_queue_service import GitOperation, GitQueueService
from app.services.helm_values_builder import render_app_values

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(**kwargs) -> types.SimpleNamespace:
    """Build a minimal Application-like namespace (no DB required)."""
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
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _make_queue_mock() -> GitQueueService:
    q = MagicMock(spec=GitQueueService)
    q.enqueue = AsyncMock(return_value=str(uuid.uuid4()))
    return q


# ---------------------------------------------------------------------------
# render_app_values — unit tests
# ---------------------------------------------------------------------------


def test_render_app_values_returns_dict():
    app = _make_app()
    result = render_app_values(app, "gemeente-a")
    assert isinstance(result, dict)
    assert result["appSlug"] == "my-app"
    assert result["tenantSlug"] == "gemeente-a"


def test_render_app_values_with_image_tag():
    app = _make_app(image_tag="harbor.example.com/haven/ns/my-app:abc123")
    result = render_app_values(app, "gemeente-a")
    assert result["image"]["tag"] == "abc123"
    assert "harbor.example.com/haven/ns/my-app" in result["image"]["repository"]


def test_render_app_values_no_image_tag():
    """When no image has been built, image tag defaults to 'latest'."""
    app = _make_app(image_tag=None)
    result = render_app_values(app, "gemeente-a")
    assert result["image"]["tag"] == "latest"


def test_render_app_values_replicas():
    app = _make_app(replicas=3)
    result = render_app_values(app, "gemeente-a")
    assert result["replicas"] == 3


def test_render_app_values_port():
    app = _make_app(port=3000)
    result = render_app_values(app, "gemeente-a")
    assert result["port"] == 3000


def test_render_app_values_env_vars():
    app = _make_app(env_vars={"DATABASE_URL": "postgres://...", "DEBUG": "true"})
    result = render_app_values(app, "gemeente-a")
    assert result["env"]["DATABASE_URL"] == "postgres://..."
    assert result["env"]["DEBUG"] == "true"


def test_render_app_values_service_secrets_extracted():
    """env_from_secrets list → service_secret_names in values."""
    app = _make_app(
        env_from_secrets=[
            {"service_name": "pg", "secret_name": "pg-credentials", "namespace": "tenant-a"},
            {"service_name": "redis", "secret_name": "redis-credentials", "namespace": "tenant-a"},
        ]
    )
    result = render_app_values(app, "gemeente-a")
    assert "pg-credentials" in result["envSecrets"]
    assert "redis-credentials" in result["envSecrets"]


def test_render_app_values_no_env_from_secrets():
    """Even without service secrets, app-level env secret is always included."""
    app = _make_app(env_from_secrets=None)
    result = render_app_values(app, "gemeente-a")
    # App-level sensitive env var secret always included for Vault/K8s Secret support
    assert f"{app.slug}-env-secrets" in result["envSecrets"]


def test_render_app_values_resources():
    app = _make_app(
        resource_cpu_request="100m",
        resource_cpu_limit="1000m",
        resource_memory_request="128Mi",
        resource_memory_limit="1Gi",
    )
    result = render_app_values(app, "gemeente-a")
    assert result["resources"]["requests"]["cpu"] == "100m"
    assert result["resources"]["limits"]["memory"] == "1Gi"


def test_render_app_values_autoscaling():
    app = _make_app(min_replicas=2, max_replicas=10, cpu_threshold=80)
    result = render_app_values(app, "gemeente-a")
    assert result["autoscaling"]["minReplicas"] == 2
    assert result["autoscaling"]["maxReplicas"] == 10
    assert result["autoscaling"]["targetCPUUtilizationPercentage"] == 80


def test_render_app_values_custom_domain():
    app = _make_app(custom_domain="myapp.gemeente.nl")
    result = render_app_values(app, "gemeente-a")
    assert result["httproute"]["customDomain"] == "myapp.gemeente.nl"


def test_render_app_values_health_check_path():
    app = _make_app(health_check_path="/healthz")
    result = render_app_values(app, "gemeente-a")
    assert result["probes"]["liveness"]["path"] == "/healthz"
    assert result["probes"]["readiness"]["path"] == "/healthz"


# ---------------------------------------------------------------------------
# PATCH /apps endpoint — queue integration tests (via HTTP client)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_app_enqueues_update_on_replicas_change(async_client, sample_tenant, db_session):
    """PATCH with replicas change must enqueue UPDATE_FILE."""
    from app.deps import get_git_queue
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    # Create an app first
    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="patch-test",
        name="Patch Test",
        repo_url="https://github.com/org/repo",
        branch="main",
        image_tag="harbor.example.com/haven/tenant-test/patch-test:abc123",
    )
    db_session.add(app_obj)
    await db_session.commit()

    mock_queue = _make_queue_mock()
    fastapi_app.dependency_overrides[get_git_queue] = lambda: mock_queue

    try:
        resp = await async_client.patch(
            f"/api/v1/tenants/{sample_tenant.slug}/apps/patch-test",
            json={"replicas": 3},
        )
        assert resp.status_code == 200
        assert resp.json()["replicas"] == 3
        mock_queue.enqueue.assert_awaited_once()
        call_args = mock_queue.enqueue.call_args
        assert call_args[0][0] == GitOperation.UPDATE_FILE
        payload = call_args[0][1]
        assert payload["tenant_slug"] == sample_tenant.slug
        assert payload["app_slug"] == "patch-test"
        assert "values" in payload
        assert "content" in payload
    finally:
        fastapi_app.dependency_overrides.pop(get_git_queue, None)


@pytest.mark.asyncio
async def test_patch_app_no_enqueue_when_queue_none(async_client, sample_tenant, db_session):
    """PATCH with queue=None must not fail and skip enqueue."""
    from app.deps import get_git_queue
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="no-queue-app",
        name="No Queue App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    fastapi_app.dependency_overrides[get_git_queue] = lambda: None

    try:
        resp = await async_client.patch(
            f"/api/v1/tenants/{sample_tenant.slug}/apps/no-queue-app",
            json={"replicas": 2},
        )
        assert resp.status_code == 200
    finally:
        fastapi_app.dependency_overrides.pop(get_git_queue, None)


@pytest.mark.asyncio
async def test_patch_app_no_enqueue_for_non_gitops_fields(async_client, sample_tenant, db_session):
    """PATCH with only non-gitops fields (e.g., branch) must not enqueue."""
    from app.deps import get_git_queue
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="branch-only",
        name="Branch Only",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    mock_queue = _make_queue_mock()
    fastapi_app.dependency_overrides[get_git_queue] = lambda: mock_queue

    try:
        resp = await async_client.patch(
            f"/api/v1/tenants/{sample_tenant.slug}/apps/branch-only",
            json={"branch": "develop"},
        )
        assert resp.status_code == 200
        mock_queue.enqueue.assert_not_awaited()
    finally:
        fastapi_app.dependency_overrides.pop(get_git_queue, None)


@pytest.mark.asyncio
async def test_patch_app_no_enqueue_when_image_tag_none(async_client, sample_tenant, db_session):
    """PATCH with gitops fields must NOT enqueue if app has no image_tag (never built).

    This prevents wiping an existing Deployment by writing empty image to values.yaml.
    """
    from app.deps import get_git_queue
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="no-image-app",
        name="No Image App",
        repo_url="https://github.com/org/repo",
        branch="main",
        image_tag=None,  # Never built — no image tag
    )
    db_session.add(app_obj)
    await db_session.commit()

    mock_queue = _make_queue_mock()
    fastapi_app.dependency_overrides[get_git_queue] = lambda: mock_queue

    try:
        resp = await async_client.patch(
            f"/api/v1/tenants/{sample_tenant.slug}/apps/no-image-app",
            json={"replicas": 5},
        )
        assert resp.status_code == 200
        assert resp.json()["replicas"] == 5
        # Must NOT enqueue — image_tag is None, would wipe deployment
        mock_queue.enqueue.assert_not_awaited()
    finally:
        fastapi_app.dependency_overrides.pop(get_git_queue, None)


# ---------------------------------------------------------------------------
# pipeline enqueue — unit test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_enqueues_image_tag_update_after_running():
    """run_pipeline must enqueue UPDATE_FILE after successful deploy."""
    import uuid as _uuid

    from app.services.pipeline import run_pipeline

    dep_id = _uuid.uuid4()
    app_id = _uuid.uuid4()
    tenant_id = _uuid.uuid4()

    # Minimal DB mocks
    mock_deployment = MagicMock()
    mock_deployment.status = None
    mock_deployment.build_job_name = None
    mock_deployment.image_tag = None

    mock_app = MagicMock()
    mock_app.image_tag = None

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(side_effect=lambda model, pk: mock_deployment if "Deployment" in str(model) else mock_app)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    mock_session_factory = MagicMock(return_value=mock_db)

    mock_k8s = MagicMock()
    mock_build_svc = AsyncMock()
    mock_build_svc.trigger_build = AsyncMock(return_value="job-abc")
    mock_build_svc.wait_for_completion = AsyncMock(return_value="succeeded")
    mock_build_svc.get_build_logs = AsyncMock(return_value="")

    mock_deploy_svc = AsyncMock()
    mock_deploy_svc.deploy = AsyncMock()
    mock_deploy_svc.wait_for_ready = AsyncMock(return_value=(True, "ready"))

    queue = _make_queue_mock()

    with (
        patch("app.services.pipeline.BuildService", return_value=mock_build_svc),
        patch("app.services.pipeline.DeployService", return_value=mock_deploy_svc),
        patch("app.services.pipeline.get_service_secret_names", new=AsyncMock(return_value=[])),
        patch("app.services.pipeline._use_gitops", return_value=False),
    ):
        await run_pipeline(
            deployment_id=dep_id,
            app_id=app_id,
            repo_url="https://github.com/org/repo",
            branch="main",
            commit_sha="abc1234567",
            app_slug="my-app",
            tenant_slug="gemeente-a",
            namespace="tenant-gemeente-a",
            tenant_id=tenant_id,
            env_vars={},
            replicas=1,
            port=8000,
            session_factory=mock_session_factory,
            k8s=mock_k8s,
            queue=queue,
        )

    queue.enqueue.assert_awaited_once()
    call_args = queue.enqueue.call_args
    assert call_args[0][0] == GitOperation.UPDATE_FILE
    payload = call_args[0][1]
    assert payload["tenant_slug"] == "gemeente-a"
    assert payload["app_slug"] == "my-app"
    assert "abc1234" in payload["commit_message"]
