"""Tests for GiteaClient and GitOpsScaffold."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.gitea_client import GiteaClient
from app.services.gitops_scaffold import GitOpsScaffold

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def _make_client(base_url: str = "http://gitea:3000", token: str = "test-token") -> GiteaClient:
    return GiteaClient(base_url=base_url, token=token)


def _make_scaffold(client: GiteaClient) -> GitOpsScaffold:
    return GitOpsScaffold(client=client, org="haven", repo="haven-gitops", branch="main")


# ---------------------------------------------------------------------------
# GiteaClient.health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_client_health_ok() -> None:
    client = _make_client()
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient") as mock_cls:
        inst = AsyncMock()
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=False)
        inst.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = inst

        result = await client.health()

    assert result is True


@pytest.mark.asyncio
async def test_gitea_client_health_fail_on_exception() -> None:
    client = _make_client()
    with patch("httpx.AsyncClient") as mock_cls:
        inst = AsyncMock()
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=False)
        inst.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_cls.return_value = inst

        result = await client.health()

    assert result is False


@pytest.mark.asyncio
async def test_gitea_client_health_unconfigured() -> None:
    client = GiteaClient(base_url="", token="")
    result = await client.health()
    assert result is False


# ---------------------------------------------------------------------------
# GiteaClient.get_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_client_get_file_found() -> None:
    client = _make_client()
    expected = {"sha": "abc123", "content": _b64("hello: world\n"), "type": "file"}

    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = expected
        result = await client.get_file("haven", "haven-gitops", "tenants/t1/kustomization.yaml")

    assert result == expected
    mock_req.assert_called_once()


@pytest.mark.asyncio
async def test_gitea_client_get_file_not_found() -> None:
    client = _make_client()

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    not_found = httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp)

    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.side_effect = not_found
        result = await client.get_file("haven", "haven-gitops", "missing/path")

    assert result is None


# ---------------------------------------------------------------------------
# GiteaClient.create_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_client_create_file() -> None:
    client = _make_client()
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"commit": {"sha": "deadbeef"}}
        sha = await client.create_file("haven", "haven-gitops", "tenants/t1/ns.yaml", "content", "msg")

    assert sha == "deadbeef"
    call_kwargs = mock_req.call_args
    # Verify base64 encoding of content
    assert call_kwargs.kwargs["json"]["content"] == _b64("content")
    assert call_kwargs.kwargs["json"]["message"] == "msg"


# ---------------------------------------------------------------------------
# GiteaClient.update_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_client_update_file() -> None:
    client = _make_client()
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"commit": {"sha": "newsha"}}
        sha = await client.update_file(
            "haven", "haven-gitops", "path/file.yaml", "new content", "oldsha123", "update msg"
        )

    assert sha == "newsha"
    call_kwargs = mock_req.call_args
    assert call_kwargs.kwargs["json"]["sha"] == "oldsha123"
    assert call_kwargs.kwargs["json"]["content"] == _b64("new content")


# ---------------------------------------------------------------------------
# GiteaClient.delete_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_client_delete_file() -> None:
    client = _make_client()
    with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"commit": {"sha": "delsha"}}
        sha = await client.delete_file("haven", "haven-gitops", "path/file.yaml", "filsha", "delete msg")

    assert sha == "delsha"
    call_kwargs = mock_req.call_args
    assert call_kwargs.kwargs["json"]["sha"] == "filsha"


# ---------------------------------------------------------------------------
# GiteaClient.upsert_file — create path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_client_upsert_creates_when_missing() -> None:
    client = _make_client()
    with (
        patch.object(client, "get_file", new_callable=AsyncMock, return_value=None),
        patch.object(client, "create_file", new_callable=AsyncMock, return_value="sha1") as mock_create,
        patch.object(client, "update_file", new_callable=AsyncMock) as mock_update,
    ):
        result = await client.upsert_file("haven", "repo", "path/f.yaml", "content", "msg")

    assert result == "sha1"
    mock_create.assert_called_once()
    mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# GiteaClient.upsert_file — update path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_client_upsert_updates_when_exists() -> None:
    client = _make_client()
    existing = {"sha": "existing-sha", "content": _b64("old content"), "type": "file"}
    with (
        patch.object(client, "get_file", new_callable=AsyncMock, return_value=existing),
        patch.object(client, "create_file", new_callable=AsyncMock) as mock_create,
        patch.object(client, "update_file", new_callable=AsyncMock, return_value="newsha") as mock_update,
    ):
        result = await client.upsert_file("haven", "repo", "path/f.yaml", "new content", "msg")

    assert result == "newsha"
    mock_create.assert_not_called()
    mock_update.assert_called_once_with("haven", "repo", "path/f.yaml", "new content", "existing-sha", "msg", "main")


# ---------------------------------------------------------------------------
# GitOpsScaffold.scaffold_tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scaffold_tenant_is_noop() -> None:
    """scaffold_tenant is now a no-op — tenant dir is created lazily by scaffold_app."""
    client = _make_client()
    scaffold = _make_scaffold(client)

    with patch.object(client, "upsert_file", new_callable=AsyncMock) as mock_upsert:
        await scaffold.scaffold_tenant("gemeente-utrecht")

    mock_upsert.assert_not_called()


# ---------------------------------------------------------------------------
# GitOpsScaffold.scaffold_app
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scaffold_app_creates_values_yaml() -> None:
    client = _make_client()
    scaffold = _make_scaffold(client)

    with patch.object(client, "upsert_file", new_callable=AsyncMock, return_value="sha") as mock_upsert:
        await scaffold.scaffold_app(
            "gemeente-utrecht",
            "backend-api",
            port=8080,
            replicas=2,
            env_vars={"DATABASE_URL": "postgresql://..."},
        )

    mock_upsert.assert_called_once()
    call = mock_upsert.call_args
    assert call.args[2] == "tenants/gemeente-utrecht/backend-api/values.yaml"
    content: str = call.args[3]
    assert "backend-api" in content
    assert "gemeente-utrecht" in content
    assert "8080" in content
    assert "DATABASE_URL" in content


# ---------------------------------------------------------------------------
# GitOpsScaffold.delete_app
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scaffold_delete_app() -> None:
    client = _make_client()
    scaffold = _make_scaffold(client)

    with patch.object(client, "delete_directory", new_callable=AsyncMock) as mock_del:
        await scaffold.delete_app("my-tenant", "my-app")

    mock_del.assert_called_once_with(
        "haven",
        "haven-gitops",
        "tenants/my-tenant/my-app",
        "Haven API: delete app my-app for tenant my-tenant",
        "main",
    )


# ---------------------------------------------------------------------------
# GitOpsScaffold.delete_tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scaffold_delete_tenant() -> None:
    client = _make_client()
    scaffold = _make_scaffold(client)

    with patch.object(client, "delete_directory", new_callable=AsyncMock) as mock_del:
        await scaffold.delete_tenant("my-tenant")

    mock_del.assert_called_once_with(
        "haven",
        "haven-gitops",
        "tenants/my-tenant",
        "Haven API: delete tenant my-tenant",
        "main",
    )


# ---------------------------------------------------------------------------
# GitOpsScaffold — unconfigured client is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scaffold_noop_when_unconfigured() -> None:
    client = GiteaClient(base_url="", token="")
    scaffold = _make_scaffold(client)

    # Should not raise, just log
    await scaffold.scaffold_tenant("test-tenant")
    await scaffold.scaffold_app("test-tenant", "test-app")
    await scaffold.delete_app("test-tenant", "test-app")
    await scaffold.delete_tenant("test-tenant")


# ---------------------------------------------------------------------------
# /internal/gitea/health endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_health_endpoint_unconfigured(async_client) -> None:
    """When Gitea is not configured the health endpoint returns configured=False."""
    resp = await async_client.get("/api/v1/internal/gitea/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["healthy"] is False
