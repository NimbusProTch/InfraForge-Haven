import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/github", tags=["github"])

GITHUB_API = "https://api.github.com"
_HEADERS = {"Accept": "application/vnd.github.v3+json"}


def _auth_headers(token: str) -> dict:
    return {**_HEADERS, "Authorization": f"token {token}"}


@router.get("/repos")
async def list_repos(token: str = Query(..., description="GitHub Personal Access Token")) -> list:
    """List repositories accessible with the provided PAT."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GITHUB_API}/user/repos",
            headers=_auth_headers(token),
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
    token: str = Query(..., description="GitHub Personal Access Token"),
) -> list:
    """List branches for a repository."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/branches",
            headers=_auth_headers(token),
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
