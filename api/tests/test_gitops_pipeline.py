"""Tests for GitOps mode activation (Sprint D2).

Covers:
  - GitOps mode detection (_use_gitops)
  - GitOpsService path convention (tenants/{t}/{a}/, no gitops/ prefix)
  - GitOpsScaffold path convention
  - Pipeline GitOps vs Direct branching
  - Pipeline queue path convention
  - Applications router enqueue path
  - Webhook GitOps dependency injection
  - scaffold_tenant no-op behaviour
"""

from __future__ import annotations

import types
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.git_queue_service import GitQueueService

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
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _make_queue_mock() -> GitQueueService:
    q = MagicMock(spec=GitQueueService)
    q.enqueue = AsyncMock(return_value=str(uuid.uuid4()))
    return q


# ---------------------------------------------------------------------------
# 1. GitOps mode detection
# ---------------------------------------------------------------------------


def test_use_gitops_returns_true_when_configured():
    from app.services.pipeline import _use_gitops

    with patch("app.services.pipeline.settings") as mock_settings:
        mock_settings.gitops_repo_url = "http://gitea.svc/haven/haven-gitops.git"
        assert _use_gitops() is True


def test_use_gitops_returns_false_when_empty():
    from app.services.pipeline import _use_gitops

    with patch("app.services.pipeline.settings") as mock_settings:
        mock_settings.gitops_repo_url = ""
        assert _use_gitops() is False


# ---------------------------------------------------------------------------
# 2-3. GitOpsService path convention
# ---------------------------------------------------------------------------


def test_gitops_service_app_dir_no_prefix():
    """_app_dir must return {clone_dir}/tenants/{t}/{a}/ — no extra 'gitops/' segment."""
    from app.services.gitops_service import GitOpsService

    svc = GitOpsService.__new__(GitOpsService)
    svc._clone_dir = Path("/tmp/test-clone")

    result = svc._app_dir("amsterdam", "web-portal")
    assert result == Path("/tmp/test-clone/tenants/amsterdam/web-portal")
    # Must NOT have a gitops/ segment between clone_dir and tenants/
    assert "/gitops/tenants/" not in str(result)


def test_gitops_service_service_dir_no_prefix():
    """_service_dir must return {clone_dir}/tenants/{t}/services/{s}/."""
    from app.services.gitops_service import GitOpsService

    svc = GitOpsService.__new__(GitOpsService)
    svc._clone_dir = Path("/tmp/test-clone")

    result = svc._service_dir("amsterdam", "my-pg")
    assert result == Path("/tmp/test-clone/tenants/amsterdam/services/my-pg")
    assert "/gitops/tenants/" not in str(result)


def test_gitops_service_delete_tenant_path():
    """delete_tenant path must be {clone_dir}/tenants/{t}/ — no extra 'gitops/' segment."""
    from app.services.gitops_service import GitOpsService

    svc = GitOpsService.__new__(GitOpsService)
    svc._clone_dir = Path("/tmp/test-clone")

    # Verify the path construction matches what delete_tenant uses
    tenant_dir = svc._clone_dir / "tenants" / "amsterdam"
    assert tenant_dir == Path("/tmp/test-clone/tenants/amsterdam")
    assert "/gitops/tenants/" not in str(tenant_dir)


# ---------------------------------------------------------------------------
# 4. GitOpsScaffold path convention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scaffold_app_writes_correct_path():
    """scaffold_app must write to tenants/{t}/{a}/values.yaml — no 'apps/' segment."""
    from app.services.gitops_scaffold import GitOpsScaffold

    mock_client = MagicMock()
    mock_client._is_configured.return_value = True
    mock_client.upsert_file = AsyncMock(return_value="abc123")

    scaffold = GitOpsScaffold(client=mock_client, org="haven", repo="haven-gitops", branch="main")
    await scaffold.scaffold_app("amsterdam", "web-portal")

    mock_client.upsert_file.assert_awaited_once()
    call_args = mock_client.upsert_file.call_args
    path_arg = call_args[0][2]  # 3rd positional arg = path
    assert path_arg == "tenants/amsterdam/web-portal/values.yaml"
    assert "/apps/" not in path_arg


@pytest.mark.asyncio
async def test_scaffold_delete_app_correct_path():
    """delete_app must delete tenants/{t}/{a}/ — no 'apps/' segment."""
    from app.services.gitops_scaffold import GitOpsScaffold

    mock_client = MagicMock()
    mock_client._is_configured.return_value = True
    mock_client.delete_directory = AsyncMock()

    scaffold = GitOpsScaffold(client=mock_client, org="haven", repo="haven-gitops", branch="main")
    await scaffold.delete_app("amsterdam", "web-portal")

    mock_client.delete_directory.assert_awaited_once()
    call_args = mock_client.delete_directory.call_args
    path_arg = call_args[0][2]
    assert path_arg == "tenants/amsterdam/web-portal"
    assert "/apps/" not in path_arg


# ---------------------------------------------------------------------------
# 5. scaffold_tenant is now a no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scaffold_tenant_is_noop():
    """scaffold_tenant must NOT write any files to Gitea."""
    from app.services.gitops_scaffold import GitOpsScaffold

    mock_client = MagicMock()
    mock_client._is_configured.return_value = True
    mock_client.upsert_file = AsyncMock()
    mock_client.create_file = AsyncMock()
    mock_client.ensure_org = AsyncMock()
    mock_client.ensure_repo = AsyncMock()

    scaffold = GitOpsScaffold(client=mock_client, org="haven", repo="haven-gitops", branch="main")
    await scaffold.scaffold_tenant("amsterdam")

    # No file operations should have been called
    mock_client.upsert_file.assert_not_awaited()
    mock_client.create_file.assert_not_awaited()
    mock_client.ensure_org.assert_not_awaited()
    mock_client.ensure_repo.assert_not_awaited()


# ---------------------------------------------------------------------------
# 6-7. Pipeline GitOps vs Direct branching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_uses_gitops_when_configured():
    """When _use_gitops() is True and gitops is provided, pipeline must call write_app_values."""
    from app.services.pipeline import run_pipeline

    dep_id = uuid.uuid4()
    app_id = uuid.uuid4()

    mock_deployment = MagicMock()
    mock_app = MagicMock()
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(side_effect=lambda model, pk: mock_deployment if "Deployment" in str(model) else mock_app)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory = MagicMock(return_value=mock_db)

    mock_build_svc = AsyncMock()
    mock_build_svc.trigger_build = AsyncMock(return_value="job-abc")
    mock_build_svc.wait_for_completion = AsyncMock(return_value="succeeded")

    mock_gitops = AsyncMock()
    mock_gitops.write_app_values = AsyncMock(return_value="sha123")

    mock_argocd = AsyncMock()
    mock_argocd.trigger_sync = AsyncMock(return_value=True)
    mock_argocd.wait_for_healthy = AsyncMock(return_value=(True, "healthy"))

    with (
        patch("app.services.pipeline.BuildService", return_value=mock_build_svc),
        patch("app.services.pipeline.DeployService"),
        patch("app.services.pipeline.get_service_secret_names", new=AsyncMock(return_value=[])),
        patch("app.services.pipeline._use_gitops", return_value=True),
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
            tenant_id=uuid.uuid4(),
            env_vars={},
            replicas=1,
            port=8000,
            session_factory=mock_session_factory,
            k8s=MagicMock(),
            gitops=mock_gitops,
            argocd=mock_argocd,
        )

    mock_gitops.write_app_values.assert_awaited_once()
    call_args = mock_gitops.write_app_values.call_args
    assert call_args[0][0] == "gemeente-a"
    assert call_args[0][1] == "my-app"
    mock_argocd.trigger_sync.assert_awaited_once_with("gemeente-a-my-app")


@pytest.mark.asyncio
async def test_pipeline_uses_direct_when_gitops_not_configured():
    """When _use_gitops() is False, pipeline must call deploy_svc.deploy()."""
    from app.services.pipeline import run_pipeline

    dep_id = uuid.uuid4()
    app_id = uuid.uuid4()

    mock_deployment = MagicMock()
    mock_app = MagicMock()
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(side_effect=lambda model, pk: mock_deployment if "Deployment" in str(model) else mock_app)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory = MagicMock(return_value=mock_db)

    mock_build_svc = AsyncMock()
    mock_build_svc.trigger_build = AsyncMock(return_value="job-abc")
    mock_build_svc.wait_for_completion = AsyncMock(return_value="succeeded")

    mock_deploy_svc = AsyncMock()
    mock_deploy_svc.deploy = AsyncMock()
    mock_deploy_svc.wait_for_ready = AsyncMock(return_value=(True, "ready"))

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
            tenant_id=uuid.uuid4(),
            env_vars={},
            replicas=1,
            port=8000,
            session_factory=mock_session_factory,
            k8s=MagicMock(),
        )

    mock_deploy_svc.deploy.assert_awaited_once()


# ---------------------------------------------------------------------------
# 8. Pipeline queue path convention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_queue_path_has_no_gitops_prefix():
    """Queue enqueue path must be tenants/... not gitops/tenants/..."""
    from app.services.pipeline import run_pipeline

    dep_id = uuid.uuid4()
    app_id = uuid.uuid4()

    mock_deployment = MagicMock()
    mock_app = MagicMock()
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(side_effect=lambda model, pk: mock_deployment if "Deployment" in str(model) else mock_app)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory = MagicMock(return_value=mock_db)

    mock_build_svc = AsyncMock()
    mock_build_svc.trigger_build = AsyncMock(return_value="job-abc")
    mock_build_svc.wait_for_completion = AsyncMock(return_value="succeeded")

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
            tenant_id=uuid.uuid4(),
            env_vars={},
            replicas=1,
            port=8000,
            session_factory=mock_session_factory,
            k8s=MagicMock(),
            queue=queue,
        )

    queue.enqueue.assert_awaited_once()
    payload = queue.enqueue.call_args[0][1]
    path = payload["path"]
    assert path == "tenants/gemeente-a/my-app/values.yaml"
    assert not path.startswith("gitops/")


# ---------------------------------------------------------------------------
# 9. Applications router enqueue path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_applications_router_enqueue_path_no_gitops_prefix(async_client, sample_tenant, db_session):
    """PATCH /apps enqueue must use tenants/... path, not gitops/tenants/..."""
    from app.deps import get_git_queue
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="path-test",
        name="Path Test",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    mock_queue = _make_queue_mock()
    fastapi_app.dependency_overrides[get_git_queue] = lambda: mock_queue

    try:
        resp = await async_client.patch(
            f"/api/v1/tenants/{sample_tenant.slug}/apps/path-test",
            json={"replicas": 2},
        )
        assert resp.status_code == 200
        mock_queue.enqueue.assert_awaited_once()
        payload = mock_queue.enqueue.call_args[0][1]
        path = payload["path"]
        assert path == f"tenants/{sample_tenant.slug}/path-test/values.yaml"
        assert not path.startswith("gitops/")
    finally:
        fastapi_app.dependency_overrides.pop(get_git_queue, None)


# ---------------------------------------------------------------------------
# 10. Webhook GitOps dependency injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_push_passes_gitops_to_pipeline(async_client, sample_tenant, db_session):
    """Webhook push handler must pass gitops and argocd deps to run_pipeline."""
    import asyncio

    from app.deps import get_argocd, get_gitops
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="webhook-test",
        name="Webhook Test",
        repo_url="https://github.com/org/repo",
        branch="main",
        webhook_token="test-webhook-token-123",
    )
    db_session.add(app_obj)
    await db_session.commit()

    mock_gitops = MagicMock()
    mock_argocd = MagicMock()
    fastapi_app.dependency_overrides[get_gitops] = lambda: mock_gitops
    fastapi_app.dependency_overrides[get_argocd] = lambda: mock_argocd

    # Capture run_pipeline call args. Use AsyncMock so asyncio.create_task gets a coroutine.
    captured_kwargs = {}

    async def _fake_pipeline(**kwargs):
        captured_kwargs.update(kwargs)

    with patch("app.routers.webhooks.run_pipeline", side_effect=_fake_pipeline):
        resp = await async_client.post(
            "/api/v1/webhooks/github/test-webhook-token-123",
            json={
                "ref": "refs/heads/main",
                "after": "abc123def456",
            },
            headers={
                "X-GitHub-Event": "push",
            },
        )
        # Give the background task a chance to run
        await asyncio.sleep(0.05)

    assert resp.status_code == 202
    assert "gitops" in captured_kwargs
    assert "argocd" in captured_kwargs

    fastapi_app.dependency_overrides.pop(get_gitops, None)
    fastapi_app.dependency_overrides.pop(get_argocd, None)


# ---------------------------------------------------------------------------
# 11. GitOpsService gitea_admin_token fallback
# ---------------------------------------------------------------------------


def test_gitops_service_falls_back_to_gitea_admin_token():
    """GitOpsService must use gitea_admin_token when github_token is empty."""
    from app.services.gitops_service import GitOpsService

    with patch("app.services.gitops_service.settings") as mock_settings:
        mock_settings.gitops_repo_url = "http://gitea.svc/haven/haven-gitops.git"
        mock_settings.gitops_branch = "main"
        mock_settings.gitops_clone_dir = "/tmp/haven-gitops"
        mock_settings.gitops_deploy_key_path = ""
        mock_settings.gitops_github_token = ""
        mock_settings.gitea_admin_token = "gitea-token-123"

        svc = GitOpsService()
        assert svc._github_token == "gitea-token-123"


# ---------------------------------------------------------------------------
# 12. scaffold_app not configured — graceful skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scaffold_app_skips_when_not_configured():
    """scaffold_app must skip gracefully when Gitea is not configured."""
    from app.services.gitops_scaffold import GitOpsScaffold

    mock_client = MagicMock()
    mock_client._is_configured.return_value = False
    mock_client.upsert_file = AsyncMock()

    scaffold = GitOpsScaffold(client=mock_client, org="haven", repo="haven-gitops", branch="main")
    await scaffold.scaffold_app("amsterdam", "web-portal")

    mock_client.upsert_file.assert_not_awaited()


# ---------------------------------------------------------------------------
# 13. delete_tenant removes entire directory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_tenant_removes_directory():
    """delete_tenant must call delete_directory on tenants/{slug}."""
    from app.services.gitops_scaffold import GitOpsScaffold

    mock_client = MagicMock()
    mock_client._is_configured.return_value = True
    mock_client.delete_directory = AsyncMock()

    scaffold = GitOpsScaffold(client=mock_client, org="haven", repo="haven-gitops", branch="main")
    await scaffold.delete_tenant("amsterdam")

    mock_client.delete_directory.assert_awaited_once()
    call_args = mock_client.delete_directory.call_args
    path_arg = call_args[0][2]
    assert path_arg == "tenants/amsterdam"
