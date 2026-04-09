"""Tests for GitHub OAuth flow and API proxy endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.routers.github import _oauth_states, _resolve_token, _store_oauth_state, _validate_oauth_state


async def _make_tenant(db, add_test_user_owner: bool = True):
    """Create a tenant. By default also adds the default async_client mock
    user (sub='test-user') as OWNER so the H0-12 membership/role check on
    /github/connect and /github/status is satisfied.
    """
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
    await db.flush()
    if add_test_user_owner:
        db.add(
            TenantMember(
                tenant_id=tenant.id,
                user_id="test-user",
                email="test@haven.nl",
                role=MemberRole("owner"),
            )
        )
    await db.commit()
    await db.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# _resolve_token helper
# ---------------------------------------------------------------------------


class TestResolveToken:
    def test_bearer_header(self):
        assert _resolve_token("Bearer ghp_abc123", None) == "ghp_abc123"

    def test_query_param_fallback(self):
        assert _resolve_token(None, "ghp_query_token") == "ghp_query_token"

    def test_bearer_takes_precedence(self):
        assert _resolve_token("Bearer ghp_header", "ghp_query") == "ghp_header"

    def test_no_token_raises_401(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _resolve_token(None, None)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# /github/auth/url
# ---------------------------------------------------------------------------


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
async def test_auth_url_preserves_scope_colons(async_client):
    """GitHub OAuth scopes with colons (read:user, read:org) must not be percent-encoded."""
    with patch("app.routers.github.settings") as mock_settings:
        mock_settings.github_client_id = "test-client-id"
        mock_settings.github_redirect_uri = "http://localhost:3000/callback"
        response = await async_client.get("/api/v1/github/auth/url")

    url = response.json()["url"]
    assert "read:user" in url
    assert "read:org" in url
    # Ensure colons are NOT encoded as %3A
    assert "read%3Auser" not in url


@pytest.mark.asyncio
async def test_auth_url_503_when_no_client_id(async_client):
    """GET /github/auth/url returns 503 when GitHub OAuth is not configured."""
    with patch("app.routers.github.settings") as mock_settings:
        mock_settings.github_client_id = ""
        response = await async_client.get("/api/v1/github/auth/url")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# /github/auth/callback
# ---------------------------------------------------------------------------


async def _get_valid_state() -> str:
    """Helper: store a state token in the in-memory fallback and return it."""
    state = "test-state-" + uuid.uuid4().hex[:8]
    # Directly add to the in-memory store (bypasses Redis)
    _oauth_states[state] = "test-tenant"
    return state


@pytest.mark.asyncio
async def test_oauth_callback_exchanges_code(async_client):
    """GET /github/auth/callback exchanges code for access_token with valid state."""
    state = await _get_valid_state()
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"access_token": "gho_exchanged_token"}

    with patch("app.routers.github.settings") as mock_settings, patch("httpx.AsyncClient") as mock_httpx:
        mock_settings.github_client_id = "cid"
        mock_settings.github_client_secret = "secret"
        mock_settings.github_redirect_uri = "http://localhost/callback"
        mock_settings.redis_url = ""

        mock_http_instance = AsyncMock()
        mock_http_instance.post = AsyncMock(return_value=mock_response)
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await async_client.get(f"/api/v1/github/auth/callback?code=test-code&state={state}")

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "gho_exchanged_token"


@pytest.mark.asyncio
async def test_oauth_callback_github_error_response(async_client):
    """GET /github/auth/callback returns 400 when GitHub says code is bad."""
    state = await _get_valid_state()
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"error": "bad_verification_code", "error_description": "Code expired"}

    with (
        patch("app.routers.github.settings") as mock_settings,
        patch("app.routers.github.httpx.AsyncClient") as mock_httpx,
    ):
        mock_settings.github_client_id = "cid"
        mock_settings.github_client_secret = "secret"
        mock_settings.github_redirect_uri = "http://localhost/callback"
        mock_settings.redis_url = ""

        mock_http_instance = AsyncMock()
        mock_http_instance.post = AsyncMock(return_value=mock_response)
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await async_client.get(f"/api/v1/github/auth/callback?code=expired&state={state}")

    assert response.status_code == 400
    assert "Code expired" in response.json()["detail"]


@pytest.mark.asyncio
async def test_oauth_callback_http_failure(async_client):
    """GET /github/auth/callback returns 502 when GitHub HTTP call fails."""
    state = await _get_valid_state()
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 500

    with (
        patch("app.routers.github.settings") as mock_settings,
        patch("app.routers.github.httpx.AsyncClient") as mock_httpx,
    ):
        mock_settings.github_client_id = "cid"
        mock_settings.github_client_secret = "secret"
        mock_settings.github_redirect_uri = "http://localhost/callback"
        mock_settings.redis_url = ""

        mock_http_instance = AsyncMock()
        mock_http_instance.post = AsyncMock(return_value=mock_response)
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await async_client.get(f"/api/v1/github/auth/callback?code=abc&state={state}")

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_oauth_callback_503_when_not_configured(async_client):
    """GET /github/auth/callback returns 503 if GitHub OAuth is not configured."""
    state = await _get_valid_state()
    with patch("app.routers.github.settings") as mock_settings:
        mock_settings.github_client_id = ""
        mock_settings.github_client_secret = ""
        mock_settings.redis_url = ""
        response = await async_client.get(f"/api/v1/github/auth/callback?code=abc&state={state}")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# CSRF State Validation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oauth_csrf_no_state_returns_422(async_client):
    """Callback without state query param returns 422 (FastAPI validation)."""
    response = await async_client.get("/api/v1/github/auth/callback?code=abc")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_oauth_csrf_invalid_state_returns_400(async_client):
    """Callback with unknown state token returns 400."""
    with patch("app.routers.github.settings") as mock_settings:
        mock_settings.github_client_id = "cid"
        mock_settings.github_client_secret = "secret"
        mock_settings.redis_url = ""
        response = await async_client.get("/api/v1/github/auth/callback?code=abc&state=invalid-state-xxx")
    assert response.status_code == 400
    assert "Invalid or expired" in response.json()["detail"]


@pytest.mark.asyncio
async def test_oauth_csrf_replay_attack_returns_400(async_client):
    """State token can only be used once (replay attack prevention)."""
    state = await _get_valid_state()
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"access_token": "gho_token"}

    with patch("app.routers.github.settings") as mock_settings, patch("httpx.AsyncClient") as mock_httpx:
        mock_settings.github_client_id = "cid"
        mock_settings.github_client_secret = "secret"
        mock_settings.github_redirect_uri = "http://localhost/callback"
        mock_settings.redis_url = ""

        mock_http_instance = AsyncMock()
        mock_http_instance.post = AsyncMock(return_value=mock_response)
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        # First use — should succeed
        r1 = await async_client.get(f"/api/v1/github/auth/callback?code=abc&state={state}")
        assert r1.status_code == 200

        # Second use — state consumed, should fail
        r2 = await async_client.get(f"/api/v1/github/auth/callback?code=abc&state={state}")
        assert r2.status_code == 400
        assert "Invalid or expired" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_oauth_state_store_and_validate():
    """State storage and validation works correctly."""
    state = "test-state-unit"
    await _store_oauth_state(state, "my-tenant")

    # First validate — should return context
    ctx = await _validate_oauth_state(state)
    assert ctx == "my-tenant"

    # Second validate — consumed, should return None
    ctx2 = await _validate_oauth_state(state)
    assert ctx2 is None


# ---------------------------------------------------------------------------
# /github/connect/{tenant_slug}  (POST + DELETE)
# ---------------------------------------------------------------------------


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
async def test_disconnect_github_404_for_unknown_tenant(async_client):
    """DELETE /github/connect/{slug} returns 404 for unknown tenant slug."""
    response = await async_client.delete("/api/v1/github/connect/nonexistent-tenant")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /github/user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_returns_profile(async_client):
    """GET /github/user returns GitHub profile with Bearer token."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = {
        "login": "testuser",
        "id": 12345,
        "name": "Test User",
        "public_repos": 10,
    }

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.github.httpx.AsyncClient", return_value=mock_http):
        response = await async_client.get(
            "/api/v1/github/user",
            headers={"Authorization": "Bearer ghp_testtoken"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["login"] == "testuser"
    assert data["id"] == 12345


@pytest.mark.asyncio
async def test_get_user_invalid_token_returns_401(async_client):
    """GET /github/user returns 401 for invalid GitHub token."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.is_success = False

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.github.httpx.AsyncClient", return_value=mock_http):
        response = await async_client.get(
            "/api/v1/github/user",
            headers={"Authorization": "Bearer bad_token"},
        )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# /github/repos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_repos_combines_user_and_org(async_client):
    """GET /github/repos merges user repos + org repos, deduplicating by id."""
    user_repos = [{"id": 1, "full_name": "user/repo1"}, {"id": 2, "full_name": "user/repo2"}]
    org_repos = [{"id": 3, "full_name": "org/repo3"}]
    orgs = [{"login": "my-org"}]

    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.is_success = True
        resp.status_code = 200
        if "/user/repos" in url:
            resp.json.return_value = user_repos
        elif "/user/orgs" in url:
            resp.json.return_value = orgs
        elif "/orgs/my-org/repos" in url:
            resp.json.return_value = org_repos
        else:
            resp.json.return_value = []
        return resp

    mock_http = AsyncMock()
    mock_http.get = mock_get
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.github.httpx.AsyncClient", return_value=mock_http):
        response = await async_client.get(
            "/api/v1/github/repos",
            headers={"Authorization": "Bearer ghp_token"},
        )

    assert response.status_code == 200
    repos = response.json()
    assert len(repos) == 3
    repo_names = [r["full_name"] for r in repos]
    assert "user/repo1" in repo_names
    assert "org/repo3" in repo_names


@pytest.mark.asyncio
async def test_list_repos_deduplicates_by_id(async_client):
    """GET /github/repos does not return duplicate repos that appear in both user and org lists."""
    shared_repo = {"id": 1, "full_name": "org/repo1"}
    orgs = [{"login": "my-org"}]

    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.is_success = True
        resp.status_code = 200
        if "/user/repos" in url:
            resp.json.return_value = [shared_repo]
        elif "/user/orgs" in url:
            resp.json.return_value = orgs
        elif "/orgs/my-org/repos" in url:
            resp.json.return_value = [shared_repo]  # duplicate
        else:
            resp.json.return_value = []
        return resp

    mock_http = AsyncMock()
    mock_http.get = mock_get
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.github.httpx.AsyncClient", return_value=mock_http):
        response = await async_client.get(
            "/api/v1/github/repos",
            headers={"Authorization": "Bearer ghp_token"},
        )

    assert response.status_code == 200
    repos = response.json()
    assert len(repos) == 1  # deduplicated by id


# ---------------------------------------------------------------------------
# /github/repos/{owner}/{repo}/branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_branches(async_client):
    """GET /github/repos/{owner}/{repo}/branches returns branch list."""
    branches = [{"name": "main"}, {"name": "develop"}]
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = branches

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.github.httpx.AsyncClient", return_value=mock_http):
        response = await async_client.get(
            "/api/v1/github/repos/owner/repo/branches",
            headers={"Authorization": "Bearer ghp_token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "main"


@pytest.mark.asyncio
async def test_list_branches_repo_not_found(async_client):
    """GET /github/repos/{owner}/{repo}/branches returns 404 for missing repo."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404
    mock_resp.is_success = False

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.github.httpx.AsyncClient", return_value=mock_http):
        response = await async_client.get(
            "/api/v1/github/repos/owner/nonexistent/branches",
            headers={"Authorization": "Bearer ghp_token"},
        )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /github/repos/{owner}/{repo}/tree
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_repo_tree(async_client):
    """GET /github/repos/{owner}/{repo}/tree returns file tree."""
    tree_data = {
        "tree": [
            {"path": "README.md", "type": "blob", "size": 100},
            {"path": "src", "type": "tree"},
            {"path": "src/main.py", "type": "blob", "size": 500},
        ]
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = tree_data

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.github.httpx.AsyncClient", return_value=mock_http):
        response = await async_client.get(
            "/api/v1/github/repos/owner/repo/tree",
            headers={"Authorization": "Bearer ghp_token"},
        )

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 3
    assert items[0]["path"] == "README.md"
    assert items[1]["type"] == "tree"


# ---------------------------------------------------------------------------
# GitHub status endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_status_not_connected(async_client, db_session):
    """GET /github/status/{slug} returns connected=false when no token."""
    tenant = await _make_tenant(db_session)
    response = await async_client.get(f"/api/v1/github/status/{tenant.slug}")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False
    assert data["github_user"] is None
    assert data["needs_reauth"] is False


@pytest.mark.asyncio
async def test_github_status_connected_valid_token(async_client, db_session):
    """GET /github/status/{slug} returns connected=true with valid token."""
    tenant = await _make_tenant(db_session)
    tenant.github_token = "ghp_valid_token"
    await db_session.commit()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.json.return_value = {"login": "testuser", "id": 123}

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.github.httpx.AsyncClient", return_value=mock_http):
        response = await async_client.get(f"/api/v1/github/status/{tenant.slug}")

    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["github_user"] == "testuser"
    assert data["needs_reauth"] is False


@pytest.mark.asyncio
async def test_github_status_expired_token(async_client, db_session):
    """GET /github/status/{slug} returns needs_reauth=true when token is expired."""
    tenant = await _make_tenant(db_session)
    tenant.github_token = "ghp_expired_token"
    await db_session.commit()

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.is_success = False

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.github.httpx.AsyncClient", return_value=mock_http):
        response = await async_client.get(f"/api/v1/github/status/{tenant.slug}")

    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False
    assert data["needs_reauth"] is True


@pytest.mark.asyncio
async def test_github_status_404_tenant(async_client):
    """GET /github/status/{slug} returns 404 for unknown tenant."""
    response = await async_client.get("/api/v1/github/status/no-such-tenant")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tenant_response_includes_github_connected(async_client, db_session):
    """GET /tenants/{slug} response includes github_connected field."""
    # _make_tenant default already adds test-user as owner — no extra membership needed.
    tenant = await _make_tenant(db_session)
    response = await async_client.get(f"/api/v1/tenants/{tenant.slug}")
    assert response.status_code == 200
    data = response.json()
    assert "github_connected" in data
    assert data["github_connected"] is False


# ---------------------------------------------------------------------------
# Self-service onboarding: /tenants/me + auto-add creator as owner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_my_tenants_empty_for_new_user(async_client):
    """GET /tenants/me returns empty list when user has no tenants."""
    response = await async_client.get("/api/v1/tenants/me")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_my_tenants_returns_owned_tenants(async_client, db_session):
    """GET /tenants/me returns tenants where user is a member."""
    # _make_tenant default already adds test-user as owner.
    tenant = await _make_tenant(db_session)

    response = await async_client.get("/api/v1/tenants/me")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["slug"] == tenant.slug


@pytest.mark.asyncio
async def test_create_tenant_adds_creator_as_owner(async_client):
    """POST /tenants must auto-add creator → GET /tenants/me returns it."""
    response = await async_client.post(
        "/api/v1/tenants",
        json={
            "name": "Auto Owner Test",
            "slug": "auto-owner-test",
        },
    )
    assert response.status_code == 201
    slug = response.json()["slug"]

    # Creator should now see this tenant in /tenants/me
    me_response = await async_client.get("/api/v1/tenants/me")
    assert me_response.status_code == 200
    my_tenants = me_response.json()
    assert any(t["slug"] == slug for t in my_tenants)


# H3a (P2.1): Removed `test_keycloak_enable_self_registration`. The
# `enable_self_registration` method on KeycloakService was dead code with
# zero production callers — only this test referenced it. Sprint H3 deleted
# the method.
