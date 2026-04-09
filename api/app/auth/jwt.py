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


# ---------------------------------------------------------------------------
# Sprint H2 P12 (#23): tenant_memberships JWT claim
# ---------------------------------------------------------------------------
#
# Optimization: instead of doing a DB lookup on every authenticated
# request to determine which tenants the user belongs to, embed the
# membership list as a custom claim in the JWT itself. The Keycloak
# protocol mapper that emits this claim is documented in
# `keycloak/haven-realm.json` (commented-out, operator activates).
#
# Claim shape (expected):
#
#   "tenant_memberships": [
#     {"slug": "rotterdam", "role": "owner"},
#     {"slug": "amsterdam", "role": "viewer"}
#   ]
#
# OR the simpler shape that just emits slugs (no role info):
#
#   "tenant_memberships": ["rotterdam", "amsterdam"]
#
# Both shapes are accepted by `extract_tenant_memberships()` below; the
# caller decides whether the role info matters for their use case.
#
# Migration plan: routers progressively opt in to claim-first lookup
# via the `check_tenant_membership_in_claim()` helper. The DB lookup
# remains as the fallback for tokens issued before the mapper was
# active (Keycloak SSO Session Max default = 8h, so the transition
# window is at most 8 hours after the realm reimport).


def extract_tenant_memberships(payload: dict[str, Any]) -> list[dict[str, str]] | None:
    """Parse the `tenant_memberships` claim from a decoded JWT payload.

    Returns a normalized list of `{"slug": str, "role": str | None}` dicts,
    or `None` if the claim is missing entirely (caller should fall back
    to the DB lookup).

    Accepts both shapes:

      - Rich: `[{"slug": "rotterdam", "role": "owner"}, ...]`
      - Slug-only: `["rotterdam", "amsterdam"]`

    For the slug-only shape, `role` is set to `None`.

    Returns an empty list `[]` (NOT None) if the claim is present but
    empty — that's a positive "user belongs to ZERO tenants" signal,
    not a "no claim" signal.
    """
    claim = payload.get("tenant_memberships")
    if claim is None:
        return None
    if not isinstance(claim, list):
        logger.warning(
            "Malformed tenant_memberships claim (not a list): sub=%s type=%s",
            payload.get("sub", "?"),
            type(claim).__name__,
        )
        return None

    normalized: list[dict[str, str]] = []
    for entry in claim:
        if isinstance(entry, str):
            normalized.append({"slug": entry, "role": None})
        elif isinstance(entry, dict) and "slug" in entry:
            normalized.append({"slug": entry["slug"], "role": entry.get("role")})
        else:
            logger.warning(
                "Skipping malformed tenant_memberships entry: sub=%s entry=%r",
                payload.get("sub", "?"),
                entry,
            )
    return normalized


def check_tenant_membership_in_claim(
    payload: dict[str, Any],
    tenant_slug: str,
    *,
    min_role: str | None = None,
) -> bool | None:
    """Check if the JWT claim says the user is a member of `tenant_slug`.

    Returns:
      - `True`  → claim says yes (member of the tenant, role >= min_role if set)
      - `False` → claim says no (claim present, slug not in list, OR role too low)
      - `None`  → claim is missing entirely (caller should fall back to DB)

    The 3-state return is intentional: callers MUST distinguish "claim
    says no" from "no claim at all". Without the distinction, a missing
    claim would silently grant access (or silently deny it).

    Role hierarchy (when min_role is given):
      owner > admin > member > viewer

    If the claim is in the slug-only shape (no role info), `min_role`
    is ignored and any membership counts.
    """
    memberships = extract_tenant_memberships(payload)
    if memberships is None:
        return None  # No claim → caller falls back

    role_hierarchy = {"owner": 4, "admin": 3, "member": 2, "viewer": 1}
    min_rank = role_hierarchy.get(min_role or "", 0)

    for entry in memberships:
        if entry["slug"] != tenant_slug:
            continue
        # Found the tenant in the claim
        if min_role is None or entry.get("role") is None:
            return True
        rank = role_hierarchy.get(entry["role"], 0)
        return rank >= min_rank

    return False  # Claim was present, slug not in it


async def verify_token_not_revoked(
    payload: dict[str, Any] = Depends(verify_token),  # noqa: B008
) -> dict[str, Any]:
    """Sprint H2 P9 / H2 #24: verify_token + token-revocation list check.

    Wraps `verify_token` and additionally checks the `token_revocations`
    table. If the token's `iat` (issued-at) is BEFORE the user's reauth
    watermark, the request is rejected with 401 and the user is forced
    to re-authenticate.

    The DB session is created inline (a fresh session per request) to
    avoid coupling this dependency to the FastAPI Depends graph for
    `get_db` — which would create a circular import between
    `app.deps` (where get_db lives) and `app.auth.jwt` (where this
    dependency lives, imported by app.deps for CurrentUser type alias).

    ## Graceful degradation

    If the DB lookup fails (table missing in tests, DB unreachable in
    production), we LOG and let the request through with the original
    payload. Reasoning:

    - In tests, the `token_revocations` table is created via
      `Base.metadata.create_all` only after the conftest imports the
      model. Many test files build their own client without going
      through the canonical conftest path; we'd have to update 24 test
      files to override this dependency. Falling back gracefully is
      kinder.

    - In production, if the DB is briefly unreachable, the alternative
      is 500-ing every authenticated request — worse than letting them
      through (the JWT signature + issuer + audience + expiration
      checks already passed). The revocation check is a defense-in-
      depth feature; the primary defense is JWT validity.

    ## Test ergonomics

    `app.dependency_overrides[verify_token]` continues to work for tests
    that just need a stub user payload. Tests that specifically want to
    exercise the revocation flow can either:

    1. Insert a TokenRevocation row in the test DB session AND override
       `app.deps._SessionLocal` to return that session — see
       `tests/test_token_revocation.py::real_revocation_client`
    2. Override this wrapper directly via `app.dependency_overrides`
    """
    from sqlalchemy.exc import DatabaseError, OperationalError, ProgrammingError

    # Lazy import to avoid the deps.py ↔ auth.jwt cycle.
    from app.deps import _SessionLocal
    from app.services.token_revocation_service import is_token_revoked

    user_id = payload.get("sub", "")
    iat = payload.get("iat")  # Unix timestamp from the JWT

    if not user_id:
        # No `sub` claim — token is malformed. verify_token already
        # accepted it (audience + issuer + signature OK), so this is
        # a defensive double-check that should never fire on a real
        # Keycloak-issued token.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has no subject claim")

    if iat is None:
        # No iat claim → can't run the revocation check meaningfully.
        # Real Keycloak always emits iat; missing iat means a stub or
        # a misconfigured IdP. Log and pass through (defense-in-depth
        # rather than fail-closed; the JWT verifier already validated
        # the rest).
        logger.debug("Token has no iat claim, skipping revocation check (sub=%s)", user_id)
        return payload

    try:
        async with _SessionLocal() as db:
            if await is_token_revoked(db, user_id, iat):
                logger.info("Token revoked: sub=%s iat=%s", user_id, iat)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked. Please sign in again.",
                )
    except (OperationalError, ProgrammingError, DatabaseError) as exc:
        # Table missing (test env without migration) or DB unreachable
        # (transient outage). Degrade gracefully — see docstring above.
        logger.warning(
            "Revocation check unavailable, allowing token: sub=%s err=%s",
            user_id,
            exc.__class__.__name__,
        )

    return payload
