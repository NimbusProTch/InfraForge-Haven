"""Tests for CronJob CRUD endpoints."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.main import app
from app.models.application import Application
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember


@pytest_asyncio.fixture
async def k8s_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Client with K8s available (batch_v1 mocked)."""
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_k8s.batch_v1 = MagicMock()
    # Mock the CronJob read to return a fake K8s object
    fake_cj = MagicMock()
    fake_cj.spec.job_template.spec = MagicMock()
    fake_cj.spec.job_template.spec.template = MagicMock()
    mock_k8s.batch_v1.read_namespaced_cron_job.return_value = fake_cj
    mock_k8s.batch_v1.create_namespaced_job.return_value = MagicMock()
    mock_k8s.batch_v1.create_namespaced_cron_job.return_value = MagicMock()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: mock_k8s
    app.dependency_overrides[verify_token] = lambda: {"sub": "test-user", "email": "test@haven.nl"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


async def _make_tenant_and_app(db: AsyncSession) -> tuple[Tenant, Application]:
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="cj-tenant",
        name="CronJob Tenant",
        namespace="tenant-cj-tenant",
        keycloak_realm="cj-tenant",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db.add(tenant)
    await db.flush()
    # H0-9: cronjobs router now enforces membership
    db.add(TenantMember(tenant_id=tenant.id, user_id="test-user", email="test@haven.nl", role=MemberRole("owner")))

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="cj-app",
        name="CronJob App",
        repo_url="https://github.com/org/repo",
        branch="main",
        resource_cpu_limit="500m",
        resource_memory_limit="256Mi",
        resource_cpu_request="100m",
        resource_memory_request="64Mi",
    )
    db.add(app_obj)
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(app_obj)
    return tenant, app_obj


@pytest.mark.asyncio
async def test_list_cronjobs_empty(async_client, db_session):
    """List cronjobs returns empty list for a new app."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    response = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_cronjob(async_client, db_session):
    """POST creates a new CronJob and returns 201."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs",
        json={
            "name": "daily-cleanup",
            "schedule": "0 2 * * *",
            "command": ["python", "manage.py", "cleanup"],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "daily-cleanup"
    assert data["schedule"] == "0 2 * * *"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_cronjob_by_id(async_client, db_session):
    """GET /{id} returns the created cronjob."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    create_resp = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs",
        json={"name": "hourly-sync", "schedule": "0 * * * *", "command": ["sync.sh"]},
    )
    cj_id = create_resp.json()["id"]

    response = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs/{cj_id}")
    assert response.status_code == 200
    assert response.json()["id"] == cj_id


@pytest.mark.asyncio
async def test_update_cronjob(async_client, db_session):
    """PATCH updates cronjob schedule."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    create_resp = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs",
        json={"name": "weekly-report", "schedule": "0 9 * * 1", "command": ["report.sh"]},
    )
    cj_id = create_resp.json()["id"]

    patch_resp = await async_client.patch(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs/{cj_id}",
        json={"schedule": "0 8 * * 1"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["schedule"] == "0 8 * * 1"


@pytest.mark.asyncio
async def test_delete_cronjob(async_client, db_session):
    """DELETE removes cronjob and returns 204."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    create_resp = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs",
        json={"name": "temp-job", "schedule": "*/5 * * * *", "command": ["ping.sh"]},
    )
    cj_id = create_resp.json()["id"]

    del_resp = await async_client.delete(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs/{cj_id}")
    assert del_resp.status_code == 204

    # Confirm gone
    get_resp = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs/{cj_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_run_cronjob_now(k8s_client, db_session):
    """POST /{id}/run triggers an immediate run (202) when K8s is available."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    create_resp = await k8s_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs",
        json={"name": "manual-job", "schedule": "0 0 1 1 *", "command": ["run.sh"]},
    )
    assert create_resp.status_code == 201
    cj_id = create_resp.json()["id"]

    run_resp = await k8s_client.post(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs/{cj_id}/run")
    assert run_resp.status_code == 202


@pytest.mark.asyncio
async def test_cronjob_missing_required_fields_rejected(async_client, db_session):
    """POST without required fields (name, schedule) returns 422."""
    tenant, app_obj = await _make_tenant_and_app(db_session)

    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/cronjobs",
        json={"command": ["run.sh"]},  # missing name and schedule
    )
    assert response.status_code == 422
