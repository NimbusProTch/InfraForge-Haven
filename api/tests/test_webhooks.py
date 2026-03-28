"""Tests for GitHub webhook handler."""

import hashlib
import hmac
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models.application import Application
from app.models.tenant import Tenant

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _make_tenant_with_app(db):
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="wh-tenant",
        name="Webhook Tenant",
        namespace="tenant-wh-tenant",
        keycloak_realm="wh-tenant",
        cpu_limit="2",
        memory_limit="4Gi",
        storage_limit="20Gi",
    )
    db.add(tenant)
    await db.flush()

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="wh-app",
        name="WH App",
        repo_url="https://github.com/org/repo",
        branch="main",
        webhook_token="test-webhook-token-abc",
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_push_queues_deployment(async_client, db_session):
    """Push webhook on correct branch queues a deployment."""
    _tenant, app_obj = await _make_tenant_with_app(db_session)

    payload = {"ref": "refs/heads/main", "after": "abc123def456"}
    body = json.dumps(payload).encode()

    with patch("app.routers.webhooks.settings") as mock_settings, \
         patch("app.routers.webhooks.asyncio.create_task", MagicMock()):
        mock_settings.webhook_secret = ""  # skip signature check
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
            },
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert "deployment_id" in data


@pytest.mark.asyncio
async def test_webhook_push_wrong_branch_ignored(async_client, db_session):
    """Push webhook on non-configured branch returns ignored."""
    _tenant, app_obj = await _make_tenant_with_app(db_session)

    payload = {"ref": "refs/heads/feature/other", "after": "deadbeef"}
    body = json.dumps(payload).encode()

    with patch("app.routers.webhooks.settings") as mock_settings, \
         patch("app.routers.webhooks.asyncio.create_task", MagicMock()):
        mock_settings.webhook_secret = ""
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            content=body,
            headers={"Content-Type": "application/json", "X-GitHub-Event": "push"},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "ignored"
    assert data["reason"] == "branch mismatch"


@pytest.mark.asyncio
async def test_webhook_unknown_token_returns_404(async_client):
    """Unknown webhook token returns 404."""
    payload = {"ref": "refs/heads/main", "after": "abc"}
    body = json.dumps(payload).encode()

    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.webhook_secret = ""
        response = await async_client.post(
            "/api/v1/webhooks/github/nonexistent-token",
            content=body,
            headers={"Content-Type": "application/json", "X-GitHub-Event": "push"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_webhook_unsupported_event_ignored(async_client, db_session):
    """Unsupported events (e.g. 'issues') are gracefully ignored."""
    _tenant, app_obj = await _make_tenant_with_app(db_session)

    payload = {"action": "opened"}
    body = json.dumps(payload).encode()

    with patch("app.routers.webhooks.settings") as mock_settings, \
         patch("app.routers.webhooks.asyncio.create_task", MagicMock()):
        mock_settings.webhook_secret = ""
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            content=body,
            headers={"Content-Type": "application/json", "X-GitHub-Event": "issues"},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_pr_opened_creates_preview(async_client, db_session):
    """pull_request opened event creates a preview environment and queues deployment."""
    _tenant, app_obj = await _make_tenant_with_app(db_session)

    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "head": {"ref": "feature/pr-branch", "sha": "pr42sha"},
        },
    }
    body = json.dumps(payload).encode()

    with patch("app.routers.webhooks.settings") as mock_settings, \
         patch("app.routers.webhooks.asyncio.create_task", MagicMock()):
        mock_settings.webhook_secret = ""
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            content=body,
            headers={"Content-Type": "application/json", "X-GitHub-Event": "pull_request"},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data.get("environment") == "pr-42"


@pytest.mark.asyncio
async def test_webhook_signature_rejected_when_secret_set(async_client, db_session):
    """Requests with invalid HMAC signature are rejected with 401."""
    _tenant, app_obj = await _make_tenant_with_app(db_session)

    payload = {"ref": "refs/heads/main", "after": "abc"}
    body = json.dumps(payload).encode()

    with patch("app.routers.webhooks.settings") as mock_settings, \
         patch("app.routers.webhooks.asyncio.create_task", MagicMock()):
        mock_settings.webhook_secret = "my-secret"
        response = await async_client.post(
            f"/api/v1/webhooks/github/{app_obj.webhook_token}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": "sha256=invalidsignature",
            },
        )

    assert response.status_code == 401
