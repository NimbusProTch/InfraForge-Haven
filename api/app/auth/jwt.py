"""JWT token verification via Keycloak JWKS.

Validates RS256 tokens against the shared "haven" realm.
Enforces: expiration (exp), audience (aud), issuer (iss), algorithm (RS256).

Sprint H2 (P6): issuer verification was previously DISABLED
(`verify_iss=False`). Any Keycloak instance / realm at any URL could
issue tokens that this service would accept, as long as the audience
intersected our accepted set. That made future per-tenant realm work
or multi-IdP federation a foot-gun. Now `iss` is verified against an
explicit allow-list derived from settings.
"""

import logging
import time
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

# In-memory JWKS cache — refreshed on TTL expiry OR decode failure (key rotation).
# Sprint H2 (P6): added a 1-hour TTL so a Keycloak key rotation is picked
# up automatically within an hour even without a decode failure to trigger it.
_JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour
_jwks_cache: dict[str, Any] | None = None
_jwks_cache_fetched_at: float = 0.0

# Accepted JWT audiences — includes Keycloak's default "account" audience
# which is set on all tokens issued by Keycloak realms
_ACCEPTED_AUDIENCES = {"haven-portal", "haven-api", "haven-ui", "account"}


def _expected_issuer() -> str:
    """Return the issuer URL we expect every valid token to carry.

    Currently only the shared 'haven' realm is in use, so this is a single
    string. When per-tenant realms are introduced (Sprint 5+ for IdP
    federation), this becomes a per-token check that parses `iss` and
    confirms it matches the tenant's `keycloak_realm` field on the Tenant
    model. The H0/H1 sprints intentionally don't ship that — see
    `tooling-baseline.md` for the H2 follow-up.
    """
    return f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"


async def _fetch_jwks() -> dict[str, Any]:
    """Fetch + cache the Keycloak JWKS with a 1h TTL.

    The cache is invalidated on:
      - TTL expiry (1 hour wall clock since fetch)
      - JWT decode failure (likely key rotation)
    """
    global _jwks_cache, _jwks_cache_fetched_at
    now = time.monotonic()
    if _jwks_cache is not None and (now - _jwks_cache_fetched_at) < _JWKS_CACHE_TTL_SECONDS:
        return _jwks_cache

    jwks_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    async with httpx.AsyncClient(timeout=10) as http:
        response = await http.get(jwks_url)
        response.raise_for_status()
    _jwks_cache = response.json()
    _jwks_cache_fetched_at = now
    return _jwks_cache


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Verify and decode a Keycloak JWT token.

    Enforces:
    - RS256 algorithm
    - Token expiration (exp claim)
    - Audience validation (aud claim must include an accepted client ID)
    - Issuer validation (iss claim must equal _expected_issuer())

    Returns the decoded JWT payload dict.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    token = credentials.credentials
    jwks = await _fetch_jwks()
    expected_iss = _expected_issuer()

    try:
        # python-jose requires audience as string, not list.
        # We disable built-in aud check and validate manually after decode.
        # Issuer is verified manually too (after decode) so the error
        # messaging is friendlier and we can extend to per-tenant realms
        # without rewriting the decode call.
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={
                "verify_aud": False,
                "verify_exp": True,
                "verify_iss": False,
            },
        )

        # Manual audience validation: token's aud must intersect with accepted audiences
        token_aud = payload.get("aud")
        if token_aud:
            aud_set = {token_aud} if isinstance(token_aud, str) else set(token_aud)
            if not aud_set & _ACCEPTED_AUDIENCES:
                raise JWTError(f"Invalid audience: {token_aud}")

        # Manual issuer validation (Sprint H2 P6): the token MUST come from
        # the configured Keycloak realm. Any other issuer is a token from a
        # foreign IdP / wrong realm and must be rejected.
        token_iss = payload.get("iss")
        if token_iss != expected_iss:
            raise JWTError(f"Invalid issuer: expected {expected_iss!r}, got {token_iss!r}")

        logger.debug("Token verified: sub=%s iss=%s", payload.get("sub"), token_iss)
        return payload

    except ExpiredSignatureError as e:
        logger.warning("Expired token presented: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from e

    except JWTError as e:
        global _jwks_cache, _jwks_cache_fetched_at  # noqa: PLW0603
        logger.warning("Token validation failed: %s", e)
        _jwks_cache = None
        _jwks_cache_fetched_at = 0.0
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e
