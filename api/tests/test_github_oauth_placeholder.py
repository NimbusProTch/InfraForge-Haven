"""Regression tests for the "GITHUB_CLIENT_ID == placeholder" class of bug.

Context: iyziops-api-secrets shipped with `GITHUB_CLIENT_ID=placeholder` as a
seed value. The pre-fix `get_auth_url` happily built a GitHub OAuth URL with
`client_id=placeholder`, which github.com resolves to a 404 — looking to the
user like *our* Connect-GitHub wizard was broken. These tests pin the guard
that rejects any well-known placeholder literal.
"""

from unittest.mock import patch

import pytest

from app.config import Settings
from app.routers.github import _effective_github_client_id


class TestEffectiveClientIdHelper:
    """_effective_github_client_id() is the single choke-point for the guard.

    Both /github/auth/url and /github/auth/callback route through it.
    """

    @pytest.mark.parametrize(
        "raw",
        [
            "placeholder",
            "PLACEHOLDER",
            "Placeholder",
            "  placeholder  ",
            "changeme",
            "change-me",
            "your-client-id",
            "xxx",
        ],
    )
    def test_placeholder_literals_map_to_empty(self, raw: str):
        with patch("app.routers.github.settings") as mock:
            mock.github_client_id = raw
            mock.github_client_id_placeholder_values = (
                "placeholder",
                "changeme",
                "change-me",
                "your-client-id",
                "xxx",
            )
            assert _effective_github_client_id() == ""

    def test_real_client_id_passes_through(self):
        with patch("app.routers.github.settings") as mock:
            mock.github_client_id = "Ov23liUCbuiXlKzAgdmZ"
            mock.github_client_id_placeholder_values = ("placeholder",)
            assert _effective_github_client_id() == "Ov23liUCbuiXlKzAgdmZ"

    def test_empty_string_stays_empty(self):
        with patch("app.routers.github.settings") as mock:
            mock.github_client_id = ""
            mock.github_client_id_placeholder_values = ("placeholder",)
            assert _effective_github_client_id() == ""

    def test_none_stays_empty(self):
        with patch("app.routers.github.settings") as mock:
            mock.github_client_id = None
            mock.github_client_id_placeholder_values = ("placeholder",)
            assert _effective_github_client_id() == ""

    def test_helper_is_defensive_when_list_is_missing(self):
        """If a future test forgets to set placeholder_values on the mock,
        the helper must not blow up — it treats the guard as disabled.
        """
        with patch("app.routers.github.settings") as mock:
            mock.github_client_id = "some-client"
            # deliberately do not set github_client_id_placeholder_values;
            # the helper must still return the value instead of raising.
            # (Access on MagicMock produces another MagicMock, which the
            #  helper should defuse via the isinstance check.)
            assert _effective_github_client_id() == "some-client"


class TestAuthUrlEndpointRejectsPlaceholder:
    @pytest.mark.asyncio
    async def test_auth_url_503_when_client_id_is_placeholder(self, async_client):
        """Full-stack: /github/auth/url must 503 when the Secret still has the seed value."""
        with patch("app.routers.github.settings") as mock:
            mock.github_client_id = "placeholder"
            mock.github_client_id_placeholder_values = ("placeholder",)
            mock.github_redirect_uri = "http://localhost:3000/callback"
            response = await async_client.get("/api/v1/github/auth/url")
        assert response.status_code == 503
        body = response.json()
        # detail message must mention GITHUB_CLIENT_ID so operators see what to fix
        assert "GITHUB_CLIENT_ID" in body["detail"]

    @pytest.mark.asyncio
    async def test_auth_url_503_detail_tells_operator_what_to_do(self, async_client):
        """Regression: the 503 detail must mention the iyziops-api-secrets Secret.
        We burned hours chasing a vague 503 last sprint."""
        with patch("app.routers.github.settings") as mock:
            mock.github_client_id = "changeme"
            mock.github_client_id_placeholder_values = ("changeme",)
            mock.github_redirect_uri = "http://localhost:3000/callback"
            response = await async_client.get("/api/v1/github/auth/url")
        assert response.status_code == 503
        assert "iyziops-api-secrets" in response.json()["detail"]


class TestSettingsStartupValidation:
    """The model_validator on Settings logs an ERROR (not fatal) when
    GITHUB_CLIENT_ID is a placeholder, so the operator sees it in pod logs
    immediately after rollout. Local dev without GitHub wired must still boot.
    """

    def test_placeholder_emits_error_log(self, caplog):
        import logging

        with caplog.at_level(logging.ERROR, logger="app.config"):
            Settings(secret_key="x", database_url="sqlite://", github_client_id="placeholder")
        assert any("placeholder" in r.getMessage().lower() for r in caplog.records)

    def test_real_value_does_not_emit_error(self, caplog):
        import logging

        with caplog.at_level(logging.ERROR, logger="app.config"):
            Settings(
                secret_key="x",
                database_url="sqlite://",
                github_client_id="Ov23liUCbuiXlKzAgdmZ",
            )
        assert not any("placeholder" in r.getMessage().lower() for r in caplog.records)

    def test_missing_value_emits_info_not_error(self, caplog):
        """Empty (not set at all) is "recommended" not "placeholder" — info level."""
        import logging

        with caplog.at_level(logging.DEBUG, logger="app.config"):
            Settings(secret_key="x", database_url="sqlite://", github_client_id="")
        # no ERROR about placeholder
        assert not any(r.levelno >= logging.ERROR and "placeholder" in r.getMessage().lower() for r in caplog.records)
