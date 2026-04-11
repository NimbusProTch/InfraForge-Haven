"""Gitea per-tenant repository management endpoints.

Sprint 3: Provides CRUD for internal Gitea repos scoped to the
tenant's Gitea organization (tenant-{slug}).
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import TenantMembership
from app.services.gitea_client import gitea_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/repos", tags=["gitea-repos"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RepoCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    default_branch: str = Field(default="main", max_length=255)


class RepoResponse(BaseModel):
    id: int
    name: str
    full_name: str
    clone_url: str
    ssh_url: str
    html_url: str
    default_branch: str
    private: bool
    empty: bool


class BranchResponse(BaseModel):
    name: str
    commit_sha: str


class TreeEntry(BaseModel):
    path: str
    type: str  # "blob" or "tree"
    size: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org_name(tenant_slug: str) -> str:
    return f"tenant-{tenant_slug}"


def _to_repo_response(data: dict[str, Any]) -> RepoResponse:
    return RepoResponse(
        id=data.get("id", 0),
        name=data.get("name", ""),
        full_name=data.get("full_name", ""),
        clone_url=data.get("clone_url", ""),
        ssh_url=data.get("ssh_url", ""),
        html_url=data.get("html_url", ""),
        default_branch=data.get("default_branch", "main"),
        private=data.get("private", True),
        empty=data.get("empty", False),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[RepoResponse])
async def list_repos(
    tenant_slug: str,
    _membership: TenantMembership,
) -> list[RepoResponse]:
    """List all Gitea repos for this tenant."""
    org = _org_name(tenant_slug)
    repos = await gitea_client.list_org_repos(org)
    return [_to_repo_response(r) for r in repos]


@router.post("", response_model=RepoResponse, status_code=status.HTTP_201_CREATED)
async def create_repo(
    tenant_slug: str,
    body: RepoCreate,
    _membership: TenantMembership,
) -> RepoResponse:
    """Create a new Gitea repo in the tenant's organization."""
    org = _org_name(tenant_slug)
    await gitea_client.ensure_repo(org, body.name, default_branch=body.default_branch)
    repo = await gitea_client.get_repo(org, body.name)
    if repo is None:
        raise HTTPException(status_code=500, detail="Repo created but not found")
    return _to_repo_response(repo)


@router.get("/{repo_name}", response_model=RepoResponse)
async def get_repo(
    tenant_slug: str,
    repo_name: str,
    _membership: TenantMembership,
) -> RepoResponse:
    """Get metadata for a single Gitea repo."""
    org = _org_name(tenant_slug)
    repo = await gitea_client.get_repo(org, repo_name)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return _to_repo_response(repo)


@router.delete("/{repo_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repo(
    tenant_slug: str,
    repo_name: str,
    _membership: TenantMembership,
) -> None:
    """Delete a Gitea repo."""
    org = _org_name(tenant_slug)
    existing = await gitea_client.get_repo(org, repo_name)
    if existing is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    await gitea_client.delete_repo(org, repo_name)


@router.get("/{repo_name}/branches", response_model=list[BranchResponse])
async def list_branches(
    tenant_slug: str,
    repo_name: str,
    _membership: TenantMembership,
) -> list[BranchResponse]:
    """List branches for a repo."""
    org = _org_name(tenant_slug)
    branches = await gitea_client.list_branches(org, repo_name)
    return [
        BranchResponse(
            name=b.get("name", ""),
            commit_sha=b.get("commit", {}).get("id", ""),
        )
        for b in branches
    ]


@router.get("/{repo_name}/tree/{ref}", response_model=list[TreeEntry])
async def get_tree(
    tenant_slug: str,
    repo_name: str,
    ref: str,
    _membership: TenantMembership,
) -> list[TreeEntry]:
    """Get file tree for a repo at the given ref (branch/tag/commit)."""
    org = _org_name(tenant_slug)
    tree = await gitea_client.get_file_tree(org, repo_name, ref)
    return [
        TreeEntry(
            path=e.get("path", ""),
            type=e.get("type", "blob"),
            size=e.get("size", 0),
        )
        for e in tree
    ]
