"""Tests for monorepo build support (dockerfile_path + build_context)."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.services.build_service import BuildService


async def _make_tenant(db: AsyncSession, slug: str = "mono-test") -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        name=f"Mono {slug}",
        namespace=f"tenant-{slug}",
        keycloak_realm=slug,
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    db.add(
        TenantMember(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            user_id="test-user",
            email="test@haven.nl",
            role=MemberRole("owner"),
        )
    )
    await db.commit()
    return tenant


async def _make_app(
    db: AsyncSession,
    tenant: Tenant,
    slug: str = "mono-app",
    dockerfile_path: str | None = None,
    build_context: str | None = None,
) -> Application:
    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Mono App",
        slug=slug,
        repo_url="https://github.com/test/monorepo",
        branch="main",
        port=8000,
        replicas=1,
        dockerfile_path=dockerfile_path,
        build_context=build_context,
        image_tag="harbor.example.com/test/mono:abc123",
    )
    db.add(app_obj)
    await db.commit()
    await db.refresh(app_obj)
    return app_obj


# ---------------------------------------------------------------------------
# Build with dockerfile_path + build_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_with_dockerfile_path(async_client, db_session):
    """POST /build should pass dockerfile_path to pipeline."""
    tenant = await _make_tenant(db_session, slug="mono-df")
    app_obj = await _make_app(db_session, tenant, slug="backend", dockerfile_path="backend/Dockerfile")

    with patch("app.routers.deployments.run_pipeline") as mock_pipeline:
        response = await async_client.post(
            f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/build",
        )

    assert response.status_code == 202
    call_kwargs = mock_pipeline.call_args.kwargs
    assert call_kwargs["dockerfile_path"] == "backend/Dockerfile"


@pytest.mark.asyncio
async def test_build_with_build_context(async_client, db_session):
    """POST /build should pass build_context to pipeline."""
    tenant = await _make_tenant(db_session, slug="mono-ctx")
    app_obj = await _make_app(db_session, tenant, slug="api-svc", build_context="services/api")

    with patch("app.routers.deployments.run_pipeline") as mock_pipeline:
        response = await async_client.post(
            f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/build",
        )

    assert response.status_code == 202
    call_kwargs = mock_pipeline.call_args.kwargs
    assert call_kwargs["build_context"] == "services/api"


@pytest.mark.asyncio
async def test_build_without_monorepo_params(async_client, db_session):
    """POST /build without monorepo params passes None."""
    tenant = await _make_tenant(db_session, slug="mono-none")
    app_obj = await _make_app(db_session, tenant, slug="simple-app")

    with patch("app.routers.deployments.run_pipeline") as mock_pipeline:
        response = await async_client.post(
            f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/build",
        )

    assert response.status_code == 202
    call_kwargs = mock_pipeline.call_args.kwargs
    assert call_kwargs["dockerfile_path"] is None
    assert call_kwargs["build_context"] is None


@pytest.mark.asyncio
async def test_app_create_with_monorepo_params(async_client, db_session):
    """POST /apps with dockerfile_path + build_context stores them."""
    tenant = await _make_tenant(db_session, slug="mono-create")

    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps",
        json={
            "name": "Backend Service",
            "slug": "backend-svc",
            "repo_url": "https://github.com/org/monorepo",
            "dockerfile_path": "backend/Dockerfile",
            "build_context": "backend",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["dockerfile_path"] == "backend/Dockerfile"
    assert data["build_context"] == "backend"


@pytest.mark.asyncio
async def test_app_update_monorepo_params(async_client, db_session):
    """PATCH /apps/{slug} can update dockerfile_path and build_context."""
    tenant = await _make_tenant(db_session, slug="mono-update")
    app_obj = await _make_app(db_session, tenant, slug="updatable")

    response = await async_client.patch(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}",
        json={"dockerfile_path": "api/Dockerfile.prod", "build_context": "api"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dockerfile_path"] == "api/Dockerfile.prod"
    assert data["build_context"] == "api"


# ---------------------------------------------------------------------------
# BuildService job manifest
# ---------------------------------------------------------------------------


def test_build_job_manifest_default_paths():
    """Without monorepo params, context and dockerfile point to /workspace."""
    k8s = MagicMock()
    svc = BuildService(k8s)
    job = svc._build_job_manifest(
        job_name="build-test-abc123-def456",
        namespace="haven-builds",
        app_slug="test-app",
        repo_url="https://github.com/org/repo",
        branch="main",
        commit_sha="abc12345",
        image_name="harbor.example.com/test/app:abc12345",
    )
    # Find buildctl container args
    buildctl = job.spec.template.spec.containers[0]
    assert "context=/workspace" in " ".join(buildctl.args)
    assert "dockerfile=/workspace" in " ".join(buildctl.args)


def test_build_job_manifest_with_monorepo():
    """With monorepo params, context and dockerfile point to subdirectories."""
    k8s = MagicMock()
    svc = BuildService(k8s)
    job = svc._build_job_manifest(
        job_name="build-test-abc123-def456",
        namespace="haven-builds",
        app_slug="test-app",
        repo_url="https://github.com/org/repo",
        branch="main",
        commit_sha="abc12345",
        image_name="harbor.example.com/test/app:abc12345",
        dockerfile_path="services/api/Dockerfile",
        build_context="services/api",
    )
    buildctl = job.spec.template.spec.containers[0]
    args_str = " ".join(buildctl.args)
    assert "context=/workspace/services/api" in args_str
    assert "dockerfile=/workspace/services/api" in args_str


def test_build_job_manifest_dockerfile_in_subdirectory():
    """Dockerfile in different dir than build context."""
    k8s = MagicMock()
    svc = BuildService(k8s)
    job = svc._build_job_manifest(
        job_name="build-test-abc123-def456",
        namespace="haven-builds",
        app_slug="test-app",
        repo_url="https://github.com/org/repo",
        branch="main",
        commit_sha="abc12345",
        image_name="harbor.example.com/test/app:abc12345",
        dockerfile_path="docker/Dockerfile.prod",
        build_context=".",
    )
    buildctl = job.spec.template.spec.containers[0]
    args_str = " ".join(buildctl.args)
    assert "context=/workspace/." in args_str
    assert "dockerfile=/workspace/docker" in args_str


# ---------------------------------------------------------------------------
# Detection service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_endpoint_exists(async_client, db_session):
    """GET /github/repos/{owner}/{repo}/detect endpoint exists."""
    # Without GitHub token, should get 401
    response = await async_client.get("/api/v1/github/repos/test/repo/detect")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_repo_tree_endpoint_exists(async_client, db_session):
    """GET /github/repos/{owner}/{repo}/tree endpoint exists."""
    response = await async_client.get("/api/v1/github/repos/test/repo/tree")
    assert response.status_code == 401
