import secrets
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Query

from app.config import settings

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
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": "repo read:user",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return {"url": f"{GITHUB_AUTH_URL}?{query}", "state": state}


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
        raise HTTPException(status_code=502, detail="GitHub token exchange failed")

    data = response.json()
    if "error" in data:
        raise HTTPException(status_code=400, detail=data.get("error_description", data["error"]))

    return {"access_token": data["access_token"]}


# ---- GitHub API proxy endpoints ----


@router.get("/repos")
async def list_repos(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None, description="Deprecated: use Authorization: Bearer header"),
) -> list:
    """List repositories accessible with the provided GitHub token."""
    t = _resolve_token(authorization, token)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GITHUB_API}/user/repos",
            headers=_auth_headers(t),
            params={"per_page": 100, "sort": "updated", "type": "all"},
            timeout=15.0,
        )
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid GitHub token")
    if not response.is_success:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {response.status_code}")
    return response.json()


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
