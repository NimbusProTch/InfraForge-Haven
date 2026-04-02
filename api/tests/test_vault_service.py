"""Tests for VaultService — HashiCorp Vault KV v2 API client."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.vault_service import VaultService


class TestVaultServiceConfig:
    def test_not_configured_when_empty(self):
        svc = VaultService(url="", token="")
        assert svc.is_configured() is False

    def test_configured_when_both_set(self):
        svc = VaultService(url="http://vault:8200", token="hvs.test")
        assert svc.is_configured() is True

    def test_not_configured_when_only_url(self):
        svc = VaultService(url="http://vault:8200", token="")
        assert svc.is_configured() is False


class TestVaultServiceOperations:
    @pytest.mark.asyncio
    async def test_write_secrets(self):
        svc = VaultService(url="http://vault:8200", token="test-token")
        with patch.object(svc, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await svc.write_secrets("rotterdam", "my-api", {"DB_PASSWORD": "secret123"})
            mock_req.assert_called_once_with(
                "POST",
                "haven/data/tenants/rotterdam/apps/my-api/secrets",
                json={"data": {"DB_PASSWORD": "secret123"}},
            )

    @pytest.mark.asyncio
    async def test_read_secrets(self):
        svc = VaultService(url="http://vault:8200", token="test-token")
        with patch.object(svc, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"data": {"data": {"DB_PASSWORD": "secret123", "API_KEY": "abc"}}}
            result = await svc.read_secrets("rotterdam", "my-api")
            assert result == {"DB_PASSWORD": "secret123", "API_KEY": "abc"}

    @pytest.mark.asyncio
    async def test_read_secrets_not_found(self):
        import httpx

        svc = VaultService(url="http://vault:8200", token="test-token")
        resp = httpx.Response(404, request=httpx.Request("GET", "http://vault:8200/v1/test"))
        with patch.object(svc, "_request", new_callable=AsyncMock, side_effect=httpx.HTTPStatusError("", request=resp.request, response=resp)):
            result = await svc.read_secrets("rotterdam", "my-api")
            assert result == {}

    @pytest.mark.asyncio
    async def test_delete_secrets(self):
        svc = VaultService(url="http://vault:8200", token="test-token")
        with patch.object(svc, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await svc.delete_secrets("rotterdam", "my-api")
            mock_req.assert_called_once_with(
                "DELETE",
                "haven/metadata/tenants/rotterdam/apps/my-api/secrets",
            )

    @pytest.mark.asyncio
    async def test_list_keys(self):
        svc = VaultService(url="http://vault:8200", token="test-token")
        with patch.object(svc, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"data": {"data": {"KEY1": "v1", "KEY2": "v2"}}}
            keys = await svc.list_keys("rotterdam", "my-api")
            assert sorted(keys) == ["KEY1", "KEY2"]
