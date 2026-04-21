import logging
import secrets
from urllib.parse import quote, urlencode

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.deps import CurrentUser, DBSession
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["github"])

GITHUB_API = "https://api.github.com"
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_HEADERS = {"Accept": "application/vnd.github.v3+json"}

# OAuth state storage — Redis-backed with in-memory fallback
_oauth_redis: aioredis.Redis | None = None
_oauth_states: dict[str, str] = {}  # fallback: state -> tenant_slug
OAUTH_STATE_TTL = 600  # 10 minutes


async def _get_oauth_redis() -> aioredis.Redis | None:
    global _oauth_redis  # noqa: PLW0603
    if _oauth_redis is not None:
        return _oauth_redis
    if settings.redis_url:
        try:
            _oauth_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await _oauth_redis.ping()
            return _oauth_redis
        except Exception:
            logger.warning("Redis unavailable for OAuth state, using in-memory fallback")
            _oauth_redis = None
    return None


async def _store_oauth_state(state: str, context: str) -> None:
    r = await _get_oauth_redis()
    if r:
        await r.setex(f"oauth:state:{state}", OAUTH_STATE_TTL, context)
    else:
        _oauth_states[state] = context


async def _validate_oauth_state(state: str) -> str | None:
    """Validate and consume an OAuth state token. Returns context or None."""
    r = await _get_oauth_redis()
    if r:
        key = f"oauth:state:{state}"
        context = await r.get(key)
        if context:
            await r.delete(key)  # one-time use
        return context
    else:
        return _oauth_states.pop(state, None)


def _resolve_token(authorization: str | None, token: str | None) -> str:
    """Resolve GitHub token from Authorization: Bearer header or legacy query param."""
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    if token:
        return token
    raise HTTPException(status_code=401, detail="GitHub token required (Authorization: Bearer <token>)")


def _auth_headers(token: str) -> dict:
    return {**_HEADERS, "Authorization": f"token {token}"}


def _effective_github_client_id() -> str:
    """Return the configured client_id, or "" if it is a known placeholder literal.

    Treating "placeholder" / "changeme" / etc. as empty prevents the popup flow
    from redirecting the user to github.com with an invalid client_id (which
    renders a GitHub-side 404 that looks like *our* bug).
    (hardcoded-scan: allow — the literals above are a rejection list, not a config.)
    """
    cid = (settings.github_client_id or "").strip()
    placeholders = getattr(settings, "github_client_id_placeholder_values", ())
    if not isinstance(placeholders, (tuple, list, set, frozenset)):
        placeholders = ()
    if cid.lower() in placeholders:
        return ""
    return cid


# ---- OAuth endpoints ----


@router.get("/auth/url")
async def get_auth_url(tenant_slug: str = Query("", description="Tenant slug for CSRF binding")) -> dict:
    """Return a GitHub OAuth authorization URL for the Connect GitHub popup flow."""
    client_id = _effective_github_client_id()
    if not client_id:
        raise HTTPException(
            status_code=503,
            detail=(
                "GitHub OAuth not configured — GITHUB_CLIENT_ID is empty or set to a "
                "placeholder. Register an OAuth App and wire it into the "
                "iyziops-api-secrets Secret."
            ),
        )

    state = secrets.token_urlsafe(32)
    # Store state in Redis (or in-memory fallback) for CSRF validation
    await _store_oauth_state(state, tenant_slug)

    # Build scope separately: urlencode encodes colon as %3A which GitHub
    # does not accept for scopes like "read:user". Use quote() with safe=":"
    # to preserve the colon while encoding the space as %20.
    scope = quote("repo read:user read:org", safe=":")
    params = {
        "client_id": client_id,
        "redirect_uri": settings.github_redirect_uri,
        "state": state,
    }
    query = urlencode(params)
    url = f"{GITHUB_AUTH_URL}?{query}&scope={scope}"
    logger.info("Generated GitHub OAuth URL for state=%s tenant=%s", state[:8], tenant_slug)
    return {"url": url, "state": state}


@router.get("/auth/callback")
async def oauth_callback(
    code: str = Query(..., description="OAuth code from GitHub"),
    state: str = Query(..., description="OAuth state for CSRF validation"),
) -> dict:
    """Exchange a GitHub OAuth code for an access token.

    Validates the state parameter against the stored value to prevent CSRF attacks.
    """
    client_id = _effective_github_client_id()
    if not client_id or not settings.github_client_secret:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")

    # CSRF validation: state must match a previously issued token
    context = await _validate_oauth_state(state)
    if context is None:
        logger.warning("OAuth callback with invalid/expired state=%s", state[:8] if state else "empty")
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state token")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            GITHUB_TOKEN_URL,
            json={
                "client_id": client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
        )

    if not response.is_success:
        logger.error("GitHub token exchange HTTP error: status=%d", response.status_code)
        raise HTTPException(status_code=502, detail="GitHub token exchange failed")

    data = response.json()
    if "error" in data:
        logger.warning("GitHub OAuth error: %s - %s", data.get("error"), data.get("error_description"))
        raise HTTPException(status_code=400, detail=data.get("error_description", data["error"]))

    access_token = data.get("access_token")
    if not access_token:
        logger.error("GitHub token exchange returned no access_token, keys: %s", list(data.keys()))
        raise HTTPException(status_code=502, detail="GitHub returned empty access token")

    logger.info("GitHub OAuth token exchange successful")
    return {"access_token": access_token}


# ---- Store token per tenant ----


class ConnectGitHubRequest(BaseModel):
    access_token: str


async def _get_tenant_with_member_check(
    tenant_slug: str,
    db: DBSession,
    current_user: dict,
    *,
    require_admin: bool = False,
) -> Tenant:
    """Look up tenant + verify caller is a member.

    H0-12: Prior to this fix, /connect/{tenant_slug} let any authenticated
    user paste an arbitrary GitHub OAuth token onto any tenant — including
    one they had no relationship to. The next build of that tenant would
    clone the attacker's repo URL with the attacker-controlled token,
    which is RCE inside the victim's namespace.

    require_admin=True: caller must be owner OR admin (for token write ops)
    require_admin=False: any membership level OK (for status read)
    """
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    user_id = current_user.get("sub", "")
    member_q = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant.id,
            TenantMember.user_id == user_id,
        )
    )
    member = member_q.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=403, detail="You are not a member of this tenant")
    if require_admin and member.role not in (MemberRole.owner, MemberRole.admin):
        raise HTTPException(
            status_code=403,
            detail="Only tenant owners and admins can manage the GitHub connection",
        )
    return tenant


@router.post("/connect/{tenant_slug}")
async def connect_github(
    tenant_slug: str,
    body: ConnectGitHubRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Store a GitHub OAuth token for a tenant (used server-side for builds)."""
    tenant = await _get_tenant_with_member_check(tenant_slug, db, current_user, require_admin=True)
    tenant.github_token = body.access_token
    await db.commit()
    logger.info("Stored GitHub token for tenant %s", tenant_slug)
    return {"status": "connected", "tenant_slug": tenant_slug}


@router.delete("/connect/{tenant_slug}")
async def disconnect_github(
    tenant_slug: str,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Remove a stored GitHub OAuth token for a tenant."""
    tenant = await _get_tenant_with_member_check(tenant_slug, db, current_user, require_admin=True)
    tenant.github_token = None
    await db.commit()
    logger.info("Removed GitHub token for tenant %s", tenant_slug)
    return {"status": "disconnected", "tenant_slug": tenant_slug}


# ---- Tenant GitHub connection status ----


@router.get("/status/{tenant_slug}")
async def github_status(
    tenant_slug: str,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Check if a tenant has a valid GitHub token connected.

    Returns: connected (bool), github_user (login if valid), needs_reauth (if token expired).
    UI uses this to show/hide the "Connect GitHub" banner on tenant dashboard.
    """
    tenant = await _get_tenant_with_member_check(tenant_slug, db, current_user)

    if not tenant.github_token:
        return {"connected": False, "github_user": None, "needs_reauth": False}

    # Validate token by calling GitHub API
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API}/user",
                headers=_auth_headers(tenant.github_token),
                timeout=10.0,
            )
        if response.status_code == 401:
            return {"connected": False, "github_user": None, "needs_reauth": True}
        if response.is_success:
            user = response.json()
            return {"connected": True, "github_user": user.get("login"), "needs_reauth": False}
    except Exception:
        logger.warning("GitHub API unreachable when checking token for %s", tenant_slug)

    # Can't reach GitHub — assume connected (token exists)
    return {"connected": True, "github_user": None, "needs_reauth": False}


# ---- GitHub API proxy endpoints ----


@router.get("/user")
async def get_user(
    authorization: str | None = Header(None),
    token: str | None = Query(None, description="Deprecated: use Authorization: Bearer header"),
) -> dict:
    """Return authenticated GitHub user info (debug/verification)."""
    t = _resolve_token(authorization, token)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GITHUB_API}/user",
            headers=_auth_headers(t),
            timeout=15.0,
        )
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid GitHub token")
    if not response.is_success:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {response.status_code}")
    data = response.json()
    return {
        "login": data.get("login"),
        "id": data.get("id"),
        "name": data.get("name"),
        "public_repos": data.get("public_repos"),
    }


@router.get("/repos")
async def list_repos(
    authorization: str | None = Header(None),
    token: str | None = Query(None, description="Deprecated: use Authorization: Bearer header"),
) -> list:
    """List repositories accessible with the provided GitHub token.

    Fetches both user repos and repos from all accessible organizations
    to ensure org repos appear even if the org hasn't approved the OAuth app
    for broader access.
    """
    t = _resolve_token(authorization, token)
    headers = _auth_headers(t)
    all_repos: list[dict] = []
    seen_ids: set[int] = set()

    async with httpx.AsyncClient() as client:
        # Fetch user's own repos (owner + collaborator + org member)
        page = 1
        while True:
            response = await client.get(
                f"{GITHUB_API}/user/repos",
                headers=headers,
                params={
                    "per_page": 100,
                    "sort": "updated",
                    "affiliation": "owner,collaborator,organization_member",
                    "page": page,
                },  # noqa: E501
                timeout=15.0,
            )
            if response.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid GitHub token")
            if not response.is_success:
                raise HTTPException(status_code=502, detail=f"GitHub API error: {response.status_code}")
            repos = response.json()
            if not repos:
                break
            for repo in repos:
                if repo["id"] not in seen_ids:
                    seen_ids.add(repo["id"])
                    all_repos.append(repo)
            if len(repos) < 100:
                break
            page += 1

        # Also fetch repos from user's organizations directly
        orgs_response = await client.get(
            f"{GITHUB_API}/user/orgs",
            headers=headers,
            params={"per_page": 100},
            timeout=15.0,
        )
        if orgs_response.is_success:
            orgs = orgs_response.json()
            for org in orgs:
                org_login = org.get("login", "")
                org_page = 1
                while True:
                    org_repos_response = await client.get(
                        f"{GITHUB_API}/orgs/{org_login}/repos",
                        headers=headers,
                        params={"per_page": 100, "sort": "updated", "page": org_page},
                        timeout=15.0,
                    )
                    if not org_repos_response.is_success:
                        logger.warning(
                            "Failed to fetch repos for org %s: %d", org_login, org_repos_response.status_code
                        )  # noqa: E501
                        break
                    org_repos = org_repos_response.json()
                    if not org_repos:
                        break
                    for repo in org_repos:
                        if repo["id"] not in seen_ids:
                            seen_ids.add(repo["id"])
                            all_repos.append(repo)
                    if len(org_repos) < 100:
                        break
                    org_page += 1
            logger.info("Fetched repos from %d organizations", len(orgs))

    logger.info("Found %d total repos for authenticated user", len(all_repos))
    return all_repos


@router.get("/repos/{owner}/{repo}/tree")
async def list_repo_tree(
    owner: str,
    repo: str,
    ref: str = "main",
    authorization: str | None = Header(None),
    token: str | None = Query(None, description="GitHub token (query param or Authorization: Bearer header)"),
) -> list:
    """List files/directories in a repository (for monorepo support)."""
    t = _resolve_token(authorization, token)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1",
            headers=_auth_headers(t),
            timeout=15.0,
        )
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid GitHub token")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Repository or ref not found")
    if not response.is_success:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {response.status_code}")
    tree = response.json().get("tree", [])
    return [{"path": item["path"], "type": item["type"], "size": item.get("size")} for item in tree]


@router.get("/repos/{owner}/{repo}/detect")
async def detect_repo_deps(
    owner: str,
    repo: str,
    ref: str = "main",
    authorization: str | None = Header(None),
    token: str | None = Query(None, description="GitHub token (query param or Authorization: Bearer header)"),
) -> dict:
    """Detect language, framework, and service dependencies for a repository."""
    from app.services.detection_service import detect_dependencies

    t = _resolve_token(authorization, token)
    return await detect_dependencies(owner, repo, branch=ref, github_token=t)


@router.get("/repos/{owner}/{repo}/branches")
async def list_branches(
    owner: str,
    repo: str,
    authorization: str | None = Header(None),
    token: str | None = Query(None, description="Deprecated: use Authorization: Bearer header"),
) -> list:
    """List branches for a repository."""
    t = _resolve_token(authorization, token)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/branches",
            headers=_auth_headers(t),
            params={"per_page": 100},
            timeout=15.0,
        )
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid GitHub token")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Repository not found")
    if not response.is_success:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {response.status_code}")
    return response.json()
