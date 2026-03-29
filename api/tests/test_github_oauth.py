"""Tests for GitHub OAuth flow and API proxy endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.tenant import Tenant


async def _make_tenant(db):
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="gh-tenant",
        name="GitHub Tenant",
        namespace="tenant-gh-tenant",
        keycloak_realm="gh-tenant",
        cpu_limit="2",
        memory_limit="4Gi",
        storage_limit="20Gi",
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@pytest.mark.asyncio
async def test_auth_url_returns_url_and_state(async_client):
    """GET /github/auth/url returns a URL and state when client ID is configured."""
    with patch("app.routers.github.settings") as mock_settings:
        mock_settings.github_client_id = "test-client-id"
        mock_settings.github_redirect_uri = "http://localhost:3000/callback"
        response = await async_client.get("/api/v1/github/auth/url")

    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert "state" in data
    assert "github.com" in data["url"]
    assert "test-client-id" in data["url"]


@pytest.mark.asyncio
async def test_auth_url_503_when_no_client_id(async_client):
    """GET /github/auth/url returns 503 when GitHub OAuth is not configured."""
    with patch("app.routers.github.settings") as mock_settings:
        mock_settings.github_client_id = ""
        response = await async_client.get("/api/v1/github/auth/url")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_connect_github_stores_token(async_client, db_session):
    """POST /github/connect/{slug} stores GitHub token on tenant."""
    tenant = await _make_tenant(db_session)

    response = await async_client.post(
        f"/api/v1/github/connect/{tenant.slug}",
        json={"access_token": "gho_test_token_123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "connected"
    assert data["tenant_slug"] == tenant.slug

    await db_session.refresh(tenant)
    assert tenant.github_token == "gho_test_token_123"


@pytest.mark.asyncio
async def test_connect_github_404_for_unknown_tenant(async_client):
    """POST /github/connect/{slug} returns 404 for unknown tenant slug."""
    response = await async_client.post(
        "/api/v1/github/connect/nonexistent-tenant",
        json={"access_token": "gho_test"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_disconnect_github_removes_token(async_client, db_session):
    """DELETE /github/connect/{slug} removes GitHub token from tenant."""
    tenant = await _make_tenant(db_session)
    tenant.github_token = "gho_some_existing_token"
    await db_session.commit()

    response = await async_client.delete(f"/api/v1/github/connect/{tenant.slug}")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "disconnected"

    await db_session.refresh(tenant)
    assert tenant.github_token is None


@pytest.mark.asyncio
async def test_oauth_callback_exchanges_code(async_client):
    """GET /github/auth/callback exchanges code for access_token."""
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"access_token": "gho_exchanged_token"}

    with patch("app.routers.github.settings") as mock_settings, patch("httpx.AsyncClient") as mock_httpx:
        mock_settings.github_client_id = "cid"
        mock_settings.github_client_secret = "secret"
        mock_settings.github_redirect_uri = "http://localhost/callback"

        mock_http_instance = AsyncMock()
        mock_http_instance.post = AsyncMock(return_value=mock_response)
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await async_client.get("/api/v1/github/auth/callback?code=test-code")

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "gho_exchanged_token"


@pytest.mark.asyncio
async def test_oauth_callback_503_when_not_configured(async_client):
    """GET /github/auth/callback returns 503 if GitHub OAuth is not configured."""
    with patch("app.routers.github.settings") as mock_settings:
        mock_settings.github_client_id = ""
        mock_settings.github_client_secret = ""
        response = await async_client.get("/api/v1/github/auth/callback?code=abc")

    assert response.status_code == 503
