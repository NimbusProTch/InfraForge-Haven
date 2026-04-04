"""JWT token verification via Keycloak JWKS.

Validates RS256 tokens against the shared "haven" realm.
Enforces: expiration (exp), audience (aud), algorithm (RS256).
"""

import logging
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

# In-memory JWKS cache — refreshed on decode failure (key rotation)
_jwks_cache: dict[str, Any] | None = None

# Accepted JWT audiences (only our client IDs — NOT the generic "account" audience)
_ACCEPTED_AUDIENCES = {"haven-portal", "haven-api", "haven-ui"}


async def _fetch_jwks() -> dict[str, Any]:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    jwks_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    async with httpx.AsyncClient(timeout=10) as http:
        response = await http.get(jwks_url)
        response.raise_for_status()
    _jwks_cache = response.json()
    return _jwks_cache


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Verify and decode a Keycloak JWT token.

    Enforces:
    - RS256 algorithm
    - Token expiration (exp claim)
    - Audience validation (aud claim must include an accepted client ID)

    Returns the decoded JWT payload dict.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    token = credentials.credentials
    jwks = await _fetch_jwks()

    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=list(_ACCEPTED_AUDIENCES),
            issuer=f"{settings.keycloak_url}/realms/{settings.keycloak_realm}",
            options={
                "verify_aud": True,
                "verify_exp": True,
                "verify_iss": True,
            },
        )
        logger.debug("Token verified: sub=%s", payload.get("sub"))
        return payload

    except ExpiredSignatureError as e:
        logger.warning("Expired token presented: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from e

    except JWTError as e:
        global _jwks_cache  # noqa: PLW0603
        logger.warning("Token validation failed: %s", e)
        _jwks_cache = None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e
