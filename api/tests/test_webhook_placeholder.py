"""Regression tests for the "WEBHOOK_SECRET == placeholder" class of bug.

Context: `iyziops-api-secrets` shipped with `WEBHOOK_SECRET=placeholder` as a
seed value. Without this guard any attacker who knows the literal could forge
a valid HMAC-SHA256 signature and trigger deployments through
`POST /webhooks/github/{token}` or `POST /webhooks/gitea/{token}`. The fix
fails-closed with 503 when the live value matches a known placeholder
literal, forcing an operator to wire a real secret before webhooks accept
any traffic.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.models.application import Application
from app.models.tenant import Tenant
from app.routers.webhooks import _is_placeholder_secret

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_tenant_with_app(db):
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="wh-ph-tenant",
        name="WH Placeholder Tenant",
        namespace="tenant-wh-ph-tenant",
        keycloak_realm="wh-ph-tenant",
        cpu_limit="2",
        memory_limit="4Gi",
        storage_limit="20Gi",
    )
    db.add(tenant)
    await db.flush()

    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="wh-ph-app",
        name="WH Placeholder App",
        repo_url="https://github.com/org/repo",
        branch="main",
        webhook_token="placeholder-regression-token",
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
# Unit: _is_placeholder_secret
# ---------------------------------------------------------------------------


class TestIsPlaceholderSecret:
    @pytest.mark.parametrize(
        "raw",
        [
            "placeholder",
            "PLACEHOLDER",
            "Placeholder",
            "  placeholder  ",
            "changeme",
            "change-me",
            "your-webhook-secret",
            "xxx",
            "secret",
            "dev-secret",
        ],
    )
    def test_known_placeholders_return_true(self, raw: str) -> None:
        with patch("app.routers.webhooks.settings") as mock:
            mock.webhook_secret_placeholder_values = (
                "placeholder",
                "changeme",
                "change-me",
                "your-webhook-secret",
                "xxx",
                "secret",
                "dev-secret",
            )
            assert _is_placeholder_secret(raw) is True

    def test_real_random_secret_returns_false(self) -> None:
        with patch("app.routers.webhooks.settings") as mock:
            mock.webhook_secret_placeholder_values = ("placeholder",)
            # 64 hex chars = 32 bytes, what `openssl rand -hex 32` emits
            assert _is_placeholder_secret("9f2b7c3a8e4d1f6a0c5b9e7d3a8f2c1b9f2b7c3a8e4d1f6a0c5b9e7d3a8f2c1b") is False

    def test_empty_string_returns_false(self) -> None:
        """Empty means "not configured" — handled by the dev-mode skip branch,
        not by this helper. Must not short-circuit to True."""
        with patch("app.routers.webhooks.settings") as mock:
            mock.webhook_secret_placeholder_values = ("placeholder",)
            assert _is_placeholder_secret("") is False

    def test_helper_is_defensive_when_tuple_missing(self) -> None:
        """If a future test forgets to set placeholder_values on the mock,
        the helper must not treat MagicMock as a match — disable the guard.
        """
        with patch("app.routers.webhooks.settings"):
            # Do NOT set webhook_secret_placeholder_values on the mock;
            # helper should return False instead of blowing up or being lenient.
            assert _is_placeholder_secret("placeholder") is False


# ---------------------------------------------------------------------------
# Integration: /webhooks/github — placeholder → 503
# ---------------------------------------------------------------------------


_PLACEHOLDER_TUPLE = (
    "placeholder",
    "changeme",
    "change-me",
    "your-webhook-secret",
    "xxx",
    "secret",
    "dev-secret",
)


class TestGitHubWebhookPlaceholderFailClosed:
    @pytest.mark.asyncio
    async def test_github_webhook_placeholder_returns_503(self, async_client, db_session) -> None:
        _tenant, app_obj = await _make_tenant_with_app(db_session)

        payload = {"ref": "refs/heads/main", "after": "abc123"}
        body = json.dumps(payload).encode()

        with (
            patch("app.routers.webhooks.settings") as mock_settings,
            patch("app.routers.webhooks.asyncio.create_task", MagicMock()),
        ):
            mock_settings.webhook_secret = "placeholder"
            mock_settings.webhook_secret_placeholder_values = _PLACEHOLDER_TUPLE
            response = await async_client.post(
                f"/api/v1/webhooks/github/{app_obj.webhook_token}",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "push",
                    # Attacker guesses the placeholder literal and forges a
                    # signature with it. Without the 503 guard this would be
                    # accepted as valid.
                    "X-Hub-Signature-256": "sha256=" + ("0" * 64),
                },
            )

        assert response.status_code == 503
        detail = response.json()["detail"]
        assert "WEBHOOK_SECRET" in detail
        assert "placeholder" in detail.lower()

    @pytest.mark.asyncio
    async def test_github_webhook_changeme_literal_also_returns_503(self, async_client, db_session) -> None:
        _tenant, app_obj = await _make_tenant_with_app(db_session)

        payload = {"ref": "refs/heads/main", "after": "abc"}
        body = json.dumps(payload).encode()

        with (
            patch("app.routers.webhooks.settings") as mock_settings,
            patch("app.routers.webhooks.asyncio.create_task", MagicMock()),
        ):
            mock_settings.webhook_secret = "changeme"
            mock_settings.webhook_secret_placeholder_values = _PLACEHOLDER_TUPLE
            response = await async_client.post(
                f"/api/v1/webhooks/github/{app_obj.webhook_token}",
                content=body,
                headers={"Content-Type": "application/json", "X-GitHub-Event": "push"},
            )
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Integration: /webhooks/gitea — placeholder → 503
# ---------------------------------------------------------------------------


class TestGiteaWebhookPlaceholderFailClosed:
    @pytest.mark.asyncio
    async def test_gitea_webhook_placeholder_returns_503(self, async_client, db_session) -> None:
        _tenant, app_obj = await _make_tenant_with_app(db_session)

        payload = {"ref": "refs/heads/main", "after": "def"}
        body = json.dumps(payload).encode()

        with (
            patch("app.routers.webhooks.settings") as mock_settings,
            patch("app.routers.webhooks.asyncio.create_task", MagicMock()),
        ):
            mock_settings.webhook_secret = "placeholder"
            mock_settings.webhook_secret_placeholder_values = _PLACEHOLDER_TUPLE
            response = await async_client.post(
                f"/api/v1/webhooks/gitea/{app_obj.webhook_token}",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Gitea-Event": "push",
                    "X-Gitea-Signature": "0" * 64,
                },
            )
        assert response.status_code == 503
        assert "Gitea" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Regression: preserving existing contracts
# ---------------------------------------------------------------------------


class TestExistingBehaviorPreserved:
    @pytest.mark.asyncio
    async def test_empty_webhook_secret_still_skips_signature_check(self, async_client, db_session) -> None:
        """Dev-mode fall-through: empty WEBHOOK_SECRET continues to skip the
        signature check. Only placeholder literals trigger 503."""
        _tenant, app_obj = await _make_tenant_with_app(db_session)

        payload = {"ref": "refs/heads/main", "after": "abc"}
        body = json.dumps(payload).encode()

        with (
            patch("app.routers.webhooks.settings") as mock_settings,
            patch("app.routers.webhooks.asyncio.create_task", MagicMock()),
        ):
            mock_settings.webhook_secret = ""
            mock_settings.webhook_secret_placeholder_values = _PLACEHOLDER_TUPLE
            response = await async_client.post(
                f"/api/v1/webhooks/github/{app_obj.webhook_token}",
                content=body,
                headers={"Content-Type": "application/json", "X-GitHub-Event": "push"},
            )

        # Dev mode: no signature header, empty secret, still 202 (queued).
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_real_secret_invalid_signature_still_returns_401(self, async_client, db_session) -> None:
        """A real (non-placeholder) secret + bad signature must still be 401,
        not 503. Placeholder handling must not swallow the existing HMAC path.
        """
        _tenant, app_obj = await _make_tenant_with_app(db_session)

        payload = {"ref": "refs/heads/main", "after": "abc"}
        body = json.dumps(payload).encode()

        with (
            patch("app.routers.webhooks.settings") as mock_settings,
            patch("app.routers.webhooks.asyncio.create_task", MagicMock()),
        ):
            mock_settings.webhook_secret = "9f2b7c3a8e4d1f6a0c5b9e7d3a8f2c1b9f2b7c3a8e4d1f6a0c5b9e7d3a8f2c1b"
            mock_settings.webhook_secret_placeholder_values = _PLACEHOLDER_TUPLE
            response = await async_client.post(
                f"/api/v1/webhooks/github/{app_obj.webhook_token}",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": "sha256=invalid",
                },
            )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Startup validator: Settings emits ERROR log on placeholder
# ---------------------------------------------------------------------------


class TestSettingsStartupValidation:
    def test_placeholder_webhook_emits_error_log(self, caplog) -> None:
        import logging

        with caplog.at_level(logging.ERROR, logger="app.config"):
            Settings(
                secret_key="x",
                database_url="sqlite://",
                webhook_secret="placeholder",
            )
        assert any(
            "webhook_secret" in r.getMessage().lower() and "placeholder" in r.getMessage().lower()
            for r in caplog.records
        )

    def test_real_webhook_secret_emits_no_error(self, caplog) -> None:
        import logging

        with caplog.at_level(logging.ERROR, logger="app.config"):
            Settings(
                secret_key="x",
                database_url="sqlite://",
                webhook_secret="9f2b7c3a8e4d1f6a0c5b9e7d3a8f2c1b9f2b7c3a8e4d1f6a0c5b9e7d3a8f2c1b",
            )
        assert not any("webhook_secret" in r.getMessage().lower() for r in caplog.records)

    def test_missing_webhook_secret_does_not_emit_error(self, caplog) -> None:
        """Empty is "recommended" not "placeholder" — should not hit ERROR level."""
        import logging

        with caplog.at_level(logging.DEBUG, logger="app.config"):
            Settings(secret_key="x", database_url="sqlite://", webhook_secret="")
        assert not any(
            r.levelno >= logging.ERROR
            and "webhook_secret" in r.getMessage().lower()
            and "placeholder" in r.getMessage().lower()
            for r in caplog.records
        )

    def test_missing_webhook_secret_emits_recommended_info(self, caplog) -> None:
        """Positive counterpart to the "no-ERROR" assertion: empty emits an INFO
        "Optional settings not configured" line listing WEBHOOK_SECRET. Catches
        a regression where someone accidentally upgrades the empty path to ERROR.
        """
        import logging

        with caplog.at_level(logging.INFO, logger="app.config"):
            Settings(secret_key="x", database_url="sqlite://", webhook_secret="")
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any(
            "optional" in r.getMessage().lower() and "webhook_secret" in r.getMessage().lower() for r in info_records
        )
