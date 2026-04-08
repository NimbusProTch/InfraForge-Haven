"""Tests for the environments endpoints (CRUD + PR webhook)."""

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.environment import Environment, EnvironmentType
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember

# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def tenant_and_app(db_session: AsyncSession):
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="env-tenant",
        name="Env Tenant",
        namespace="tenant-env-tenant",
        keycloak_realm="env-tenant",
    )
    db_session.add(tenant)
    await db_session.flush()
    # H0-9: environments router now enforces membership
    db_session.add(
        TenantMember(tenant_id=tenant.id, user_id="test-user", email="test@haven.nl", role=MemberRole("owner"))
    )

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="env-app",
        name="Env App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(app_obj)
    return tenant, app_obj


# ---------------------------------------------------------------------------
# Environment CRUD
# ---------------------------------------------------------------------------


async def test_create_staging_environment(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments",
        json={"name": "staging", "env_type": "staging", "branch": "staging"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "staging"
    assert data["env_type"] == "staging"
    assert data["branch"] == "staging"
    assert data["status"] == "pending"
    assert data["domain"] is not None
    assert "staging" in data["domain"]


async def test_list_environments_empty(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    response = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_environments_returns_all(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    # Create two environments
    await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments",
        json={"name": "staging", "env_type": "staging", "branch": "staging"},
    )
    await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments",
        json={"name": "pr-1", "env_type": "preview", "branch": "feature/foo"},
    )
    response = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments")
    assert response.status_code == 200
    names = [e["name"] for e in response.json()]
    assert "staging" in names
    assert "pr-1" in names


async def test_get_environment_not_found(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    response = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments/nonexistent")
    assert response.status_code == 404


async def test_get_environment_ok(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments",
        json={"name": "staging", "env_type": "staging", "branch": "staging"},
    )
    response = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments/staging")
    assert response.status_code == 200
    assert response.json()["name"] == "staging"


async def test_duplicate_environment_name_rejected(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    payload = {"name": "staging", "env_type": "staging", "branch": "staging"}
    r1 = await async_client.post(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments", json=payload)
    assert r1.status_code == 201
    r2 = await async_client.post(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments", json=payload)
    assert r2.status_code == 409


async def test_update_environment_branch(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments",
        json={"name": "staging", "env_type": "staging", "branch": "staging"},
    )
    response = await async_client.patch(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments/staging",
        json={"branch": "develop"},
    )
    assert response.status_code == 200
    assert response.json()["branch"] == "develop"


async def test_delete_environment(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments",
        json={"name": "staging", "env_type": "staging", "branch": "staging"},
    )
    response = await async_client.delete(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments/staging")
    assert response.status_code == 204
    # Verify it's gone
    get_response = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments/staging")
    assert get_response.status_code == 404


async def test_cannot_delete_production_environment(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments",
        json={"name": "production", "env_type": "production", "branch": "main"},
    )
    response = await async_client.delete(f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments/production")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Domain computation
# ---------------------------------------------------------------------------


async def test_staging_environment_domain(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments",
        json={"name": "staging", "env_type": "staging", "branch": "staging"},
    )
    assert response.status_code == 201
    domain = response.json()["domain"]
    # Should contain "staging-" prefix
    assert domain.startswith("staging-")


async def test_preview_environment_domain(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments",
        json={"name": "pr-42", "env_type": "preview", "branch": "feature/foo"},
    )
    assert response.status_code == 201
    domain = response.json()["domain"]
    # Should contain "pr-None-" because pr_number not set via CRUD (set by webhook)
    assert "pr" in domain


async def test_production_environment_domain(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    response = await async_client.post(
        f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/environments",
        json={"name": "production", "env_type": "production", "branch": "main"},
    )
    assert response.status_code == 201
    domain = response.json()["domain"]
    # Production domain should not have staging- or pr- prefix
    assert not domain.startswith("staging-")
    assert not domain.startswith("pr-")


# ---------------------------------------------------------------------------
# PR webhook → preview environment
# ---------------------------------------------------------------------------


async def test_webhook_pr_opened_creates_preview(async_client: AsyncClient, tenant_and_app, db_session: AsyncSession):
    tenant, app_obj = tenant_and_app

    pr_payload = {
        "action": "opened",
        "number": 42,
        "pull_request": {
            "number": 42,
            "head": {"ref": "feature/my-feature", "sha": "abc12345"},
        },
    }

    with patch("app.routers.webhooks.asyncio.create_task"):
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            json=pr_payload,
            headers={"X-GitHub-Event": "pull_request"},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["environment"] == "pr-42"
    assert "url" in data

    # Verify environment was created in DB
    from sqlalchemy import select

    result = await db_session.execute(
        select(Environment).where(
            Environment.application_id == app_obj.id,
            Environment.name == "pr-42",
        )
    )
    env = result.scalar_one_or_none()
    assert env is not None
    assert env.env_type == EnvironmentType.preview
    assert env.pr_number == 42
    assert env.branch == "feature/my-feature"


async def test_webhook_pr_synchronize_updates_preview(
    async_client: AsyncClient, tenant_and_app, db_session: AsyncSession
):
    tenant, app_obj = tenant_and_app

    pr_head_v1 = {"number": 7, "head": {"ref": "fix/bug", "sha": "aaa"}}
    pr_head_v2 = {"number": 7, "head": {"ref": "fix/bug", "sha": "bbb"}}
    with patch("app.routers.webhooks.asyncio.create_task"):
        # Open PR first
        await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            json={"action": "opened", "number": 7, "pull_request": pr_head_v1},
            headers={"X-GitHub-Event": "pull_request"},
        )
        # Synchronize (new commit pushed)
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            json={"action": "synchronize", "number": 7, "pull_request": pr_head_v2},
            headers={"X-GitHub-Event": "pull_request"},
        )

    assert response.status_code == 202
    assert response.json()["environment"] == "pr-7"


async def test_webhook_pr_closed_deletes_preview(async_client: AsyncClient, tenant_and_app, db_session: AsyncSession):
    tenant, app_obj = tenant_and_app

    pr_99 = {"number": 99, "head": {"ref": "feat/x", "sha": "ccc"}}
    with patch("app.routers.webhooks.asyncio.create_task"):
        # Open PR
        await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            json={"action": "opened", "number": 99, "pull_request": pr_99},
            headers={"X-GitHub-Event": "pull_request"},
        )
        # Close PR
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            json={"action": "closed", "number": 99, "pull_request": pr_99},
            headers={"X-GitHub-Event": "pull_request"},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "deleted"
    assert data["environment"] == "pr-99"

    # Verify environment is gone from DB
    from sqlalchemy import select

    result = await db_session.execute(
        select(Environment).where(
            Environment.application_id == app_obj.id,
            Environment.name == "pr-99",
        )
    )
    assert result.scalar_one_or_none() is None


async def test_webhook_pr_closed_no_environment_is_ignored(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    with patch("app.routers.webhooks.asyncio.create_task"):
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            json={"action": "closed", "number": 999, "pull_request": {"number": 999, "head": {"ref": "x", "sha": "z"}}},
            headers={"X-GitHub-Event": "pull_request"},
        )
    assert response.status_code == 202
    assert response.json()["status"] == "ignored"


async def test_webhook_push_still_works(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    with patch("app.routers.webhooks.asyncio.create_task"):
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            json={"ref": "refs/heads/main", "after": "deadbeef"},
            headers={"X-GitHub-Event": "push"},
        )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"


async def test_webhook_unknown_event_ignored(async_client: AsyncClient, tenant_and_app):
    tenant, app_obj = tenant_and_app
    with patch("app.routers.webhooks.asyncio.create_task"):
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            json={},
            headers={"X-GitHub-Event": "deployment"},
        )
    assert response.status_code == 202
    assert response.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# 404 / tenant not found guards
# ---------------------------------------------------------------------------


async def test_environments_tenant_not_found(async_client: AsyncClient):
    response = await async_client.get("/api/v1/tenants/no-such-tenant/apps/app/environments")
    assert response.status_code == 404


async def test_environments_app_not_found(async_client: AsyncClient, tenant_and_app):
    tenant, _ = tenant_and_app
    response = await async_client.get(f"/api/v1/tenants/{tenant.slug}/apps/no-such-app/environments")
    assert response.status_code == 404
