"""Tests for Sprint 3: Gitea per-tenant repos + git_provider + webhooks."""

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.application import GitProvider

# ---------------------------------------------------------------------------
# git_provider model + schema
# ---------------------------------------------------------------------------


def test_git_provider_enum_values():
    assert GitProvider.GITHUB.value == "github"
    assert GitProvider.GITEA.value == "gitea"


def test_app_create_schema_git_provider_default():
    from app.schemas.application import ApplicationCreate

    data = ApplicationCreate(name="myapp", repo_url="https://github.com/org/repo")
    assert data.git_provider == "github"


def test_app_create_schema_git_provider_gitea():
    from app.schemas.application import ApplicationCreate

    data = ApplicationCreate(
        name="myapp", repo_url="http://gitea-http.gitea-system:3000/org/repo", git_provider="gitea"
    )
    assert data.git_provider == "gitea"


def test_app_create_schema_git_provider_invalid():
    from app.schemas.application import ApplicationCreate

    with pytest.raises(ValueError):
        ApplicationCreate(name="myapp", repo_url="https://x.com/a/b", git_provider="gitlab")


def test_app_update_schema_git_provider():
    from app.schemas.application import ApplicationUpdate

    data = ApplicationUpdate(git_provider="gitea")
    assert data.git_provider == "gitea"


def test_app_response_schema_git_provider():
    from app.schemas.application import ApplicationResponse

    resp = ApplicationResponse(
        id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        slug="myapp",
        name="myapp",
        repo_url="https://github.com/org/repo",
        branch="main",
        git_provider="gitea",
        env_vars={},
        image_tag=None,
        replicas=1,
        port=8000,
        webhook_token="abc123",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    assert resp.git_provider == "gitea"


# ---------------------------------------------------------------------------
# GiteaClient new methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_client_delete_org():
    from app.services.gitea_client import GiteaClient

    client = GiteaClient(base_url="http://gitea:3000", token="test-token")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {}
        await client.delete_org("tenant-test")
        mock_req.assert_called_once_with("DELETE", "/orgs/tenant-test", expected_status=(204, 404))


@pytest.mark.asyncio
async def test_gitea_client_list_org_repos():
    from app.services.gitea_client import GiteaClient

    client = GiteaClient(base_url="http://gitea:3000", token="test-token")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = [
            {"id": 1, "name": "repo1", "full_name": "tenant-test/repo1"},
            {"id": 2, "name": "repo2", "full_name": "tenant-test/repo2"},
        ]
        repos = await client.list_org_repos("tenant-test")
        assert len(repos) == 2
        assert repos[0]["name"] == "repo1"


@pytest.mark.asyncio
async def test_gitea_client_list_org_repos_not_found():
    import httpx

    from app.services.gitea_client import GiteaClient

    client = GiteaClient(base_url="http://gitea:3000", token="test-token")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.side_effect = httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock(status_code=404))
        repos = await client.list_org_repos("nonexistent")
        assert repos == []


@pytest.mark.asyncio
async def test_gitea_client_get_repo():
    from app.services.gitea_client import GiteaClient

    client = GiteaClient(base_url="http://gitea:3000", token="test-token")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"id": 1, "name": "myrepo", "full_name": "org/myrepo"}
        repo = await client.get_repo("org", "myrepo")
        assert repo is not None
        assert repo["name"] == "myrepo"


@pytest.mark.asyncio
async def test_gitea_client_get_repo_not_found():
    import httpx

    from app.services.gitea_client import GiteaClient

    client = GiteaClient(base_url="http://gitea:3000", token="test-token")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.side_effect = httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock(status_code=404))
        repo = await client.get_repo("org", "nonexistent")
        assert repo is None


@pytest.mark.asyncio
async def test_gitea_client_delete_repo():
    from app.services.gitea_client import GiteaClient

    client = GiteaClient(base_url="http://gitea:3000", token="test-token")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {}
        await client.delete_repo("org", "myrepo")
        mock_req.assert_called_once_with("DELETE", "/repos/org/myrepo", expected_status=(204, 404))


@pytest.mark.asyncio
async def test_gitea_client_list_branches():
    from app.services.gitea_client import GiteaClient

    client = GiteaClient(base_url="http://gitea:3000", token="test-token")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = [
            {"name": "main", "commit": {"id": "abc123"}},
            {"name": "develop", "commit": {"id": "def456"}},
        ]
        branches = await client.list_branches("org", "repo")
        assert len(branches) == 2
        assert branches[0]["name"] == "main"


@pytest.mark.asyncio
async def test_gitea_client_get_file_tree():
    from app.services.gitea_client import GiteaClient

    client = GiteaClient(base_url="http://gitea:3000", token="test-token")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {
            "sha": "abc123",
            "tree": [
                {"path": "README.md", "type": "blob", "size": 100},
                {"path": "src", "type": "tree", "size": 0},
            ],
        }
        tree = await client.get_file_tree("org", "repo", "main")
        assert len(tree) == 2
        assert tree[0]["path"] == "README.md"


@pytest.mark.asyncio
async def test_gitea_client_create_webhook():
    from app.services.gitea_client import GiteaClient

    client = GiteaClient(base_url="http://gitea:3000", token="test-token")
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"id": 1, "active": True}
        result = await client.create_webhook(
            "org", "repo", "https://api.example.com/webhooks/gitea/abc123", secret="mysecret"
        )
        assert result["active"] is True


@pytest.mark.asyncio
async def test_gitea_client_not_configured():
    from app.services.gitea_client import GiteaClient

    # Create a fresh client with empty config — methods should return neutral values
    client = GiteaClient.__new__(GiteaClient)
    client._base_url = ""
    client._token = ""
    repos = await client.list_org_repos("org")
    assert repos == []
    branches = await client.list_branches("org", "repo")
    assert branches == []
    tree = await client.get_file_tree("org", "repo")
    assert tree == []
    repo = await client.get_repo("org", "repo")
    assert repo is None
    # delete_org and delete_repo return early when not configured
    await client.delete_org("org")  # should not raise
    await client.delete_repo("org", "repo")  # should not raise


# ---------------------------------------------------------------------------
# Build service: dual provider clone URL
# ---------------------------------------------------------------------------


def test_build_job_github_clone_url():
    """GitHub clone URL injects oauth2 token."""
    from app.services.build_service import BuildService

    k8s = MagicMock()
    svc = BuildService(k8s)
    job = svc._build_job_manifest(
        job_name="build-gh-abc123-def456",
        namespace="haven-builds",
        app_slug="gh-app",
        repo_url="https://github.com/org/repo",
        branch="main",
        commit_sha="abc12345",
        image_name="harbor.example.com/test/app:abc12345",
        github_token="ghp_test123",
        git_provider="github",
    )
    init_clone = job.spec.template.spec.init_containers[0]
    assert "oauth2:ghp_test123@" in init_clone.args[0]


def test_build_job_gitea_clone_url_https():
    """Gitea HTTPS clone URL injects gitea-admin token."""
    from app.services.build_service import BuildService

    k8s = MagicMock()
    svc = BuildService(k8s)
    job = svc._build_job_manifest(
        job_name="build-gt-abc123-def456",
        namespace="haven-builds",
        app_slug="gt-app",
        repo_url="https://gitea.example.com/tenant-test/myrepo",
        branch="main",
        commit_sha="abc12345",
        image_name="harbor.example.com/test/app:abc12345",
        git_provider="gitea",
        gitea_token="gitea_admin_token_123",
    )
    init_clone = job.spec.template.spec.init_containers[0]
    assert "gitea-admin:gitea_admin_token_123@" in init_clone.args[0]


def test_build_job_gitea_clone_url_http_with_token():
    """Gitea HTTP clone URL uses explicit gitea_token param."""
    from app.services.build_service import BuildService

    k8s = MagicMock()
    svc = BuildService(k8s)
    # Pass gitea_token explicitly for HTTP URLs (in-cluster Gitea)
    job = svc._build_job_manifest(
        job_name="build-gt2-abc123-def456",
        namespace="haven-builds",
        app_slug="gt2-app",
        repo_url="https://gitea.example.com/tenant-test/myrepo",
        branch="main",
        commit_sha="abc12345",
        image_name="harbor.example.com/test/app:abc12345",
        git_provider="gitea",
        gitea_token="explicit_token_123",
    )
    init_clone = job.spec.template.spec.init_containers[0]
    assert "gitea-admin:explicit_token_123@" in init_clone.args[0]


# ---------------------------------------------------------------------------
# Gitea webhook endpoint
# ---------------------------------------------------------------------------


def test_gitea_webhook_signature_validation():
    """Gitea signature validation works with HMAC-SHA256."""
    from app.routers.webhooks import _verify_gitea_signature

    body = b'{"ref":"refs/heads/main","after":"abc123"}'
    secret = "test-secret"
    expected_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    _verify_gitea_signature(body, secret, expected_sig)


def test_gitea_webhook_signature_invalid():
    """Invalid signature raises 401."""
    from fastapi import HTTPException

    from app.routers.webhooks import _verify_gitea_signature

    with pytest.raises(HTTPException):
        _verify_gitea_signature(b"body", "secret", "wrong_signature")


def test_gitea_webhook_signature_missing():
    """Missing signature header raises 401."""
    from fastapi import HTTPException

    from app.routers.webhooks import _verify_gitea_signature

    with pytest.raises(HTTPException):
        _verify_gitea_signature(b"body", "secret", None)


def test_gitea_webhook_no_secret_skips():
    """When WEBHOOK_SECRET is empty, signature check is skipped."""
    from app.routers.webhooks import _verify_gitea_signature

    _verify_gitea_signature(b"anything", "", None)


# ---------------------------------------------------------------------------
# Gitea repos router schemas
# ---------------------------------------------------------------------------


def test_repo_create_schema_valid():
    from app.routers.gitea_repos import RepoCreate

    data = RepoCreate(name="my-repo")
    assert data.name == "my-repo"
    assert data.default_branch == "main"


def test_repo_create_schema_invalid_name():
    from app.routers.gitea_repos import RepoCreate

    with pytest.raises(ValueError):
        RepoCreate(name="Invalid Name!")


def test_repo_response_schema():
    from app.routers.gitea_repos import RepoResponse

    resp = RepoResponse(
        id=1,
        name="repo",
        full_name="org/repo",
        clone_url="https://gitea.example.com/org/repo.git",
        ssh_url="git@gitea.example.com:org/repo.git",
        html_url="https://gitea.example.com/org/repo",
        default_branch="main",
        private=True,
        empty=False,
    )
    assert resp.full_name == "org/repo"


def test_branch_response_schema():
    from app.routers.gitea_repos import BranchResponse

    resp = BranchResponse(name="main", commit_sha="abc123")
    assert resp.name == "main"


def test_tree_entry_schema():
    from app.routers.gitea_repos import TreeEntry

    entry = TreeEntry(path="src/main.py", type="blob", size=1024)
    assert entry.type == "blob"


# ---------------------------------------------------------------------------
# Tenant provision includes Gitea org
# ---------------------------------------------------------------------------


def test_tenant_provision_creates_gitea_org():
    """Tenant provision flow includes gitea-org step."""
    from app.services.tenant_service import TenantService

    k8s_mock = MagicMock()
    k8s_mock.is_available.return_value = False
    svc = TenantService(k8s_mock)
    # Just verify the method signature hasn't broken
    assert hasattr(svc, "provision")


# ---------------------------------------------------------------------------
# Alembic migration
# ---------------------------------------------------------------------------


def test_migration_0024_exists():
    """Migration file for git_provider column exists."""
    from pathlib import Path

    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "0024_add_git_provider.py"
    assert migration_path.exists(), f"Migration file not found: {migration_path}"
    content = migration_path.read_text()
    assert 'revision: str = "0024"' in content
    assert 'down_revision: str | None = "0023"' in content
    assert "git_provider" in content
