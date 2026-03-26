import logging
import secrets
from typing import Optional
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.deps import DBSession
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["github"])

GITHUB_API = "https://api.github.com"
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_HEADERS = {"Accept": "application/vnd.github.v3+json"}


def _resolve_token(authorization: Optional[str], token: Optional[str]) -> str:
    """Resolve GitHub token from Authorization: Bearer header or legacy query param."""
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    if token:
        return token
    raise HTTPException(status_code=401, detail="GitHub token required (Authorization: Bearer <token>)")


def _auth_headers(token: str) -> dict:
    return {**_HEADERS, "Authorization": f"token {token}"}


# ---- OAuth endpoints ----


@router.get("/auth/url")
async def get_auth_url() -> dict:
    """Return a GitHub OAuth authorization URL for the Connect GitHub popup flow."""
    if not settings.github_client_id:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured (GITHUB_CLIENT_ID missing)")

    state = secrets.token_urlsafe(16)
    # Build scope separately: urlencode encodes colon as %3A which GitHub
    # does not accept for scopes like "read:user". Use quote() with safe=":"
    # to preserve the colon while encoding the space as %20.
    scope = quote("repo read:user read:org", safe=":")
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "state": state,
    }
    query = urlencode(params)
    url = f"{GITHUB_AUTH_URL}?{query}&scope={scope}"
    logger.info("Generated GitHub OAuth URL for state=%s", state[:8])
    return {"url": url, "state": state}


@router.get("/auth/callback")
async def oauth_callback(code: str = Query(..., description="OAuth code from GitHub")) -> dict:
    """Exchange a GitHub OAuth code for an access token."""
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            GITHUB_TOKEN_URL,
            json={
                "client_id": settings.github_client_id,
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


@router.post("/connect/{tenant_slug}")
async def connect_github(
    tenant_slug: str,
    body: ConnectGitHubRequest,
    db: DBSession,
) -> dict:
    """Store a GitHub OAuth token for a tenant (used server-side for builds)."""
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.github_token = body.access_token
    await db.commit()
    logger.info("Stored GitHub token for tenant %s", tenant_slug)
    return {"status": "connected", "tenant_slug": tenant_slug}


@router.delete("/connect/{tenant_slug}")
async def disconnect_github(
    tenant_slug: str,
    db: DBSession,
) -> dict:
    """Remove a stored GitHub OAuth token for a tenant."""
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.github_token = None
    await db.commit()
    logger.info("Removed GitHub token for tenant %s", tenant_slug)
    return {"status": "disconnected", "tenant_slug": tenant_slug}


# ---- GitHub API proxy endpoints ----


@router.get("/user")
async def get_user(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None, description="Deprecated: use Authorization: Bearer header"),
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
    return {"login": data.get("login"), "id": data.get("id"), "name": data.get("name"), "public_repos": data.get("public_repos")}


@router.get("/repos")
async def list_repos(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None, description="Deprecated: use Authorization: Bearer header"),
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
                params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member", "page": page},
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
                        logger.warning("Failed to fetch repos for org %s: %d", org_login, org_repos_response.status_code)
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


@router.get("/repos/{owner}/{repo}/branches")
async def list_branches(
    owner: str,
    repo: str,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None, description="Deprecated: use Authorization: Bearer header"),
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
