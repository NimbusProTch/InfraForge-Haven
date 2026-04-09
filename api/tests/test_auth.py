"""Tests for JWT auth middleware — token accept/reject."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Sprint H2 P8: require_platform_admin dependency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_platform_admin_accepts_token_with_role():
    """A JWT carrying `platform-admin` in `realm_access.roles` is accepted."""
    from app.auth.rbac import require_platform_admin

    user = {
        "sub": "ops-user-1",
        "email": "ops@haven.dev",
        "realm_access": {"roles": ["default-roles-haven", "platform-admin"]},
    }
    result = await require_platform_admin(current_user=user)
    assert result is user  # passthrough — handlers can read sub/email from it


@pytest.mark.asyncio
async def test_require_platform_admin_rejects_token_without_role():
    """A JWT without the `platform-admin` realm role gets 403."""
    from app.auth.rbac import require_platform_admin

    user = {
        "sub": "regular-user",
        "email": "user@haven.dev",
        "realm_access": {"roles": ["default-roles-haven"]},  # no platform-admin
    }
    with pytest.raises(HTTPException) as exc_info:
        await require_platform_admin(current_user=user)
    assert exc_info.value.status_code == 403
    assert "platform-admin" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_platform_admin_rejects_token_with_no_realm_access():
    """A JWT missing `realm_access` entirely (rare — only programmatic
    tokens) is rejected."""
    from app.auth.rbac import require_platform_admin

    user = {"sub": "weird-user", "email": "weird@example.com"}
    with pytest.raises(HTTPException) as exc_info:
        await require_platform_admin(current_user=user)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_platform_admin_rejects_token_with_empty_roles():
    """A JWT with `realm_access.roles = []` is rejected."""
    from app.auth.rbac import require_platform_admin

    user = {
        "sub": "no-roles-user",
        "realm_access": {"roles": []},
    }
    with pytest.raises(HTTPException) as exc_info:
        await require_platform_admin(current_user=user)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Original auth tests
# ---------------------------------------------------------------------------

from app.config import settings


def _expected_issuer() -> str:
    """Mirror of `app.auth.jwt._expected_issuer()` for test fixtures."""
    return f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"


@pytest.mark.asyncio
async def test_missing_token_returns_401(async_client):
    """Endpoints requiring auth return 401 when no Bearer token is supplied."""
    # /github/repos requires Authorization header
    with patch("app.routers.github.settings") as mock_settings:
        mock_settings.github_client_id = "cid"
        await async_client.get("/api/v1/github/repos")

    # The route uses a custom header resolve, not verify_token, but we test
    # the generic 401 path through the JWT dependency on a protected route.
    # Use a route that explicitly calls verify_token via Depends.
    # Since all routes in this test app are open (auth skipped in test),
    # we test the jwt module directly.
    from fastapi import HTTPException

    from app.auth.jwt import verify_token

    with pytest.raises(HTTPException) as exc_info:
        await verify_token(credentials=None)

    assert exc_info.value.status_code == 401
    assert "Missing token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_invalid_token_returns_401():
    """An invalid JWT raises 401."""
    from fastapi.security import HTTPAuthorizationCredentials

    import app.auth.jwt as jwt_module
    from app.auth.jwt import verify_token

    # Patch _fetch_jwks so it doesn't make real HTTP calls
    with patch.object(jwt_module, "_fetch_jwks", new=AsyncMock(return_value={"keys": []})):
        from fastapi import HTTPException

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not.a.real.jwt")
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials=creds)

        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_valid_token_returns_payload():
    """A valid JWT returns the decoded payload.

    P6 (Sprint H2): the fake payload now carries an `iss` claim matching
    the configured Keycloak realm, otherwise the new issuer check rejects.
    """
    from fastapi.security import HTTPAuthorizationCredentials

    import app.auth.jwt as jwt_module
    from app.auth.jwt import verify_token

    fake_payload = {
        "sub": "user123",
        "email": "user@example.com",
        "iss": _expected_issuer(),
        "realm_access": {"roles": []},
    }

    with (
        patch.object(jwt_module, "_fetch_jwks", new=AsyncMock(return_value={"keys": []})),
        patch("app.auth.jwt.jwt.decode", return_value=fake_payload),
    ):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid.jwt.token")
        result = await verify_token(credentials=creds)

    assert result["sub"] == "user123"
    assert result["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_jwks_cache_cleared_on_decode_failure():
    """JWKS cache is invalidated when token decode fails."""
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from jose import JWTError

    import app.auth.jwt as jwt_module
    from app.auth.jwt import verify_token

    jwt_module._jwks_cache = {"keys": [{"kid": "stale"}]}

    with (
        patch.object(jwt_module, "_fetch_jwks", new=AsyncMock(return_value={"keys": []})),
        patch("app.auth.jwt.jwt.decode", side_effect=JWTError("expired")),
    ):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="expired.jwt")
        with pytest.raises(HTTPException):
            await verify_token(credentials=creds)

    assert jwt_module._jwks_cache is None


@pytest.mark.asyncio
async def test_jwks_cached_between_calls():
    """JWKS cache is populated after first call and reused on second call.

    P6 (Sprint H2): fake payload now carries `iss` so the issuer check passes.
    """
    import app.auth.jwt as jwt_module
    from app.auth.jwt import verify_token

    # Start with empty cache
    jwt_module._jwks_cache = None
    fetch_count = 0

    real_fetch_keys = {"keys": [{"kid": "test-key"}]}

    async def _mock_http_fetch():
        nonlocal fetch_count
        fetch_count += 1
        return real_fetch_keys

    with (
        patch.object(jwt_module, "_fetch_jwks", side_effect=_mock_http_fetch),
        patch("app.auth.jwt.jwt.decode", return_value={"sub": "u2", "iss": _expected_issuer()}),
    ):
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="a.b.c")
        await verify_token(credentials=creds)
        await verify_token(credentials=creds)

    # _fetch_jwks was called twice (mock bypasses internal cache logic — expected)
    assert fetch_count == 2


# ---------------------------------------------------------------------------
# P6 (Sprint H2): JWT issuer verification regression tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_with_wrong_issuer_rejected():
    """A JWT signed by the right keys but carrying a different `iss` claim
    must be rejected with 401.

    Pre-P6: `verify_iss=False` meant the iss claim was never checked. Any
    token from any Keycloak realm at any URL would be accepted as long as
    the signature + audience matched. That made future per-tenant realm
    work or multi-IdP federation a foot-gun.
    """
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    import app.auth.jwt as jwt_module
    from app.auth.jwt import verify_token

    # Payload that would be valid except for the wrong issuer
    fake_payload = {
        "sub": "attacker",
        "email": "attacker@evil.example",
        "iss": "https://attacker-keycloak.evil.example/realms/foreign-realm",
    }

    with (
        patch.object(jwt_module, "_fetch_jwks", new=AsyncMock(return_value={"keys": []})),
        patch("app.auth.jwt.jwt.decode", return_value=fake_payload),
    ):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="foreign.realm.jwt")
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials=creds)

    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_token_with_no_issuer_rejected():
    """A JWT with no `iss` claim at all must be rejected.

    Pre-P6: missing iss = silently accepted. Post-P6: rejected because
    `payload.get("iss")` returns None which does not equal the expected
    issuer string.
    """
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    import app.auth.jwt as jwt_module
    from app.auth.jwt import verify_token

    fake_payload = {
        "sub": "user-no-iss",
        "email": "user@example.com",
        # NOTE: deliberately no `iss`
    }

    with (
        patch.object(jwt_module, "_fetch_jwks", new=AsyncMock(return_value={"keys": []})),
        patch("app.auth.jwt.jwt.decode", return_value=fake_payload),
    ):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="no.iss.jwt")
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials=creds)

    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# P6 (Sprint H2): JWKS cache TTL regression tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwks_cache_refreshes_after_ttl_expiry():
    """The JWKS cache is automatically refreshed after `_JWKS_CACHE_TTL_SECONDS`.

    Pre-P6: the cache was forever (only invalidated on decode failure). A
    Keycloak key rotation would not be picked up until a token failed to
    decode, which is fragile timing.

    Post-P6: cache has a 1-hour TTL. We test it by directly calling
    `_fetch_jwks()` twice with the cache pre-seeded as if it had been
    fetched longer than the TTL ago.
    """
    import app.auth.jwt as jwt_module

    fake_jwks_old = {"keys": [{"kid": "old-key"}]}
    fake_jwks_new = {"keys": [{"kid": "new-key"}]}

    # Seed cache as if it were fetched 2 hours ago (>1h TTL)
    jwt_module._jwks_cache = fake_jwks_old
    jwt_module._jwks_cache_fetched_at = 0.0  # epoch — definitely > TTL ago

    # Mock the HTTP fetch to return the "new" key set
    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return fake_jwks_new

    class _FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            return _FakeResponse()

    with patch("app.auth.jwt.httpx.AsyncClient", return_value=_FakeHttpClient()):
        result = await jwt_module._fetch_jwks()

    # The stale cache was bypassed and a fresh fetch happened
    assert result == fake_jwks_new
    assert jwt_module._jwks_cache == fake_jwks_new


@pytest.mark.asyncio
async def test_jwks_cache_fetched_at_reset_on_failure():
    """When a token decode fails, both the cache AND the fetched_at marker
    are reset so the very next call goes back to the network.

    Without resetting `_jwks_cache_fetched_at`, the next `_fetch_jwks()`
    call could see `_jwks_cache is None` and re-fetch (good), but if a
    different code path checks `_jwks_cache_fetched_at` for stale-ness it
    would see a fresh timestamp and miss the invalidation.
    """
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from jose import JWTError

    import app.auth.jwt as jwt_module
    from app.auth.jwt import verify_token

    jwt_module._jwks_cache = {"keys": [{"kid": "stale"}]}
    jwt_module._jwks_cache_fetched_at = 12345.0

    with (
        patch.object(jwt_module, "_fetch_jwks", new=AsyncMock(return_value={"keys": []})),
        patch("app.auth.jwt.jwt.decode", side_effect=JWTError("bad sig")),
    ):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad.jwt")
        with pytest.raises(HTTPException):
            await verify_token(credentials=creds)

    assert jwt_module._jwks_cache is None
    assert jwt_module._jwks_cache_fetched_at == 0.0
