"""Tests for Sprint 3.5 critical fixes.

Covers:
- Task 2c: Repo change clears image_tag
- Task 4: Build with branch override + env vars
- Task 7: Deploy with replicas + resource limit overrides
- Task 8: App restart endpoint
- Task 6: Service update with tier change
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_tenant(db: AsyncSession, slug: str = "s35-test") -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        name=f"Sprint35 {slug}",
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
            role=MemberRole.owner,
        )
    )
    await db.commit()
    return tenant


async def _make_app(db: AsyncSession, tenant: Tenant, slug: str = "test-app") -> Application:
    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Test App",
        slug=slug,
        repo_url="https://github.com/test/repo",
        branch="main",
        port=8000,
        replicas=1,
        image_tag="harbor.example.com/test/repo:abc123",
    )
    db.add(app_obj)
    await db.commit()
    await db.refresh(app_obj)
    return app_obj


async def _make_service(
    db: AsyncSession, tenant: Tenant, name: str = "app-db", svc_type: ServiceType = ServiceType.POSTGRES
) -> ManagedService:
    svc = ManagedService(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name=name,
        service_type=svc_type,
        tier=ServiceTier.DEV,
        status=ServiceStatus.READY,
    )
    db.add(svc)
    await db.commit()
    await db.refresh(svc)
    return svc


# ---------------------------------------------------------------------------
# Task 2c: Repo change clears image_tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_app_repo_clears_image_tag(async_client, db_session):
    """When repo_url changes via PATCH, image_tag should be cleared."""
    ac = async_client
    tenant = await _make_tenant(db_session)
    app_obj = await _make_app(db_session, tenant)
    assert app_obj.image_tag is not None

    response = await ac.patch(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}",
        json={"repo_url": "https://github.com/new/repo"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["image_tag"] is None


@pytest.mark.asyncio
async def test_patch_app_branch_keeps_image_tag(async_client, db_session):
    """When only branch changes, image_tag should remain."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-branch")
    app_obj = await _make_app(db_session, tenant)
    old_tag = app_obj.image_tag

    response = await ac.patch(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}",
        json={"branch": "develop"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["image_tag"] == old_tag


@pytest.mark.asyncio
async def test_patch_app_same_repo_keeps_image_tag(async_client, db_session):
    """When repo_url is the same, image_tag should remain."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-same")
    app_obj = await _make_app(db_session, tenant)
    old_tag = app_obj.image_tag

    response = await ac.patch(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}",
        json={"repo_url": app_obj.repo_url},
    )
    assert response.status_code == 200
    assert response.json()["image_tag"] == old_tag


# ---------------------------------------------------------------------------
# Task 4: Build with branch override + env vars
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_with_branch_override(async_client, db_session):
    """POST /build with branch override should use provided branch."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-build")
    app_obj = await _make_app(db_session, tenant)

    with patch("app.routers.deployments.run_pipeline") as mock_pipeline:
        response = await ac.post(
            f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/build",
            json={"branch": "develop"},
        )

    assert response.status_code == 202
    # Verify pipeline was called with "develop" branch
    mock_pipeline.assert_called_once()
    call_kwargs = mock_pipeline.call_args.kwargs
    assert call_kwargs["branch"] == "develop"


@pytest.mark.asyncio
async def test_build_without_branch_uses_default(async_client, db_session):
    """POST /build without body uses app's default branch."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-build-def")
    app_obj = await _make_app(db_session, tenant)

    with patch("app.routers.deployments.run_pipeline") as mock_pipeline:
        response = await ac.post(
            f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/build",
        )

    assert response.status_code == 202
    call_kwargs = mock_pipeline.call_args.kwargs
    assert call_kwargs["branch"] == "main"


@pytest.mark.asyncio
async def test_build_with_env_vars(async_client, db_session):
    """POST /build with build_env_vars should merge with app env vars."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-build-env")
    app_obj = await _make_app(db_session, tenant)

    with patch("app.routers.deployments.run_pipeline") as mock_pipeline:
        response = await ac.post(
            f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/build",
            json={"build_env_vars": {"DEBUG": "true", "NODE_ENV": "production"}},
        )

    assert response.status_code == 202
    call_kwargs = mock_pipeline.call_args.kwargs
    assert call_kwargs["env_vars"]["DEBUG"] == "true"
    assert call_kwargs["env_vars"]["NODE_ENV"] == "production"


# ---------------------------------------------------------------------------
# Task 7: Deploy with replicas + resource overrides
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_with_replicas_override(async_client, db_session):
    """POST /deploy with replicas should update app and deploy."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-deploy-rep")
    app_obj = await _make_app(db_session, tenant)
    assert app_obj.replicas == 1

    response = await ac.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/deploy",
        json={"replicas": 3},
    )
    assert response.status_code == 202

    # Verify app replicas updated
    await db_session.refresh(app_obj)
    assert app_obj.replicas == 3


@pytest.mark.asyncio
async def test_deploy_with_resource_limits(async_client, db_session):
    """POST /deploy with resource limits should update app."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-deploy-res")
    app_obj = await _make_app(db_session, tenant)

    response = await ac.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/deploy",
        json={"resource_cpu_limit": "1", "resource_memory_limit": "1Gi"},
    )
    assert response.status_code == 202

    await db_session.refresh(app_obj)
    assert app_obj.resource_cpu_limit == "1"
    assert app_obj.resource_memory_limit == "1Gi"


@pytest.mark.asyncio
async def test_deploy_without_body_uses_defaults(async_client, db_session):
    """POST /deploy without body uses existing app config."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-deploy-none")
    app_obj = await _make_app(db_session, tenant)

    response = await ac.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/deploy",
    )
    assert response.status_code == 202


# ---------------------------------------------------------------------------
# Task 8: App restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_restart(async_client, db_session, mock_k8s):
    """POST /restart should patch K8s deployment with restart annotation."""
    mock_k8s.is_available.return_value = True
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-restart")
    app_obj = await _make_app(db_session, tenant)

    response = await ac.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/restart",
    )
    assert response.status_code == 202
    assert response.json()["status"] == "restarting"

    # Verify K8s patch was called
    mock_k8s.apps_v1.patch_namespaced_deployment.assert_called_once()


@pytest.mark.asyncio
async def test_app_restart_cluster_unavailable(async_client, db_session, mock_k8s):
    """POST /restart returns 503 when cluster is down."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-restart-err")
    await _make_app(db_session, tenant)

    response = await ac.post(
        f"/api/v1/tenants/{tenant.slug}/apps/test-app/restart",
    )
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Task 6: Service update with tier change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_update_replicas(async_client, db_session):
    """PATCH /services/{name} with replicas updates the service."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-svc-rep")
    svc = await _make_service(db_session, tenant)

    with patch("app.routers.services.ManagedServiceProvisioner") as MockProv:
        mock_inst = AsyncMock()
        MockProv.return_value = mock_inst

        response = await ac.patch(
            f"/api/v1/tenants/{tenant.slug}/services/{svc.name}",
            json={"replicas": 3},
        )

    assert response.status_code == 200
    mock_inst.update.assert_called_once()


@pytest.mark.asyncio
async def test_service_update_not_ready(async_client, db_session):
    """PATCH /services/{name} on non-READY service returns 409."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-svc-busy")
    svc = await _make_service(db_session, tenant, name="busy-db")
    svc.status = ServiceStatus.PROVISIONING
    await db_session.commit()

    response = await ac.patch(
        f"/api/v1/tenants/{tenant.slug}/services/{svc.name}",
        json={"replicas": 3},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_service_tier_upgrade(async_client, db_session):
    """PATCH /services/{name} with tier=prod applies prod defaults."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-svc-tier")
    svc = await _make_service(db_session, tenant, name="tier-db")
    assert svc.tier == ServiceTier.DEV

    with patch("app.routers.services.ManagedServiceProvisioner") as MockProv:
        mock_inst = AsyncMock()
        MockProv.return_value = mock_inst

        response = await ac.patch(
            f"/api/v1/tenants/{tenant.slug}/services/{svc.name}",
            json={"tier": "prod"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "prod"
    # Verify provisioner was called with prod defaults (replicas=3)
    call_kwargs = mock_inst.update.call_args.kwargs
    assert call_kwargs.get("replicas") == 3


@pytest.mark.asyncio
async def test_service_update_empty_body(async_client, db_session):
    """PATCH /services/{name} with no fields returns 422."""
    ac = async_client
    tenant = await _make_tenant(db_session, slug="s35-svc-empty")
    svc = await _make_service(db_session, tenant, name="empty-db")

    response = await ac.patch(
        f"/api/v1/tenants/{tenant.slug}/services/{svc.name}",
        json={},
    )
    assert response.status_code == 422
