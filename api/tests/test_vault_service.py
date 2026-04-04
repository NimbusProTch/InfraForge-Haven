"""Tests for VaultService and SecretService Vault integration."""

from unittest.mock import AsyncMock, MagicMock, patch

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
        with patch.object(
            svc,
            "_request",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError("", request=resp.request, response=resp),
        ):
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


# ---------------------------------------------------------------------------
# SecretService Vault integration
# ---------------------------------------------------------------------------


class TestSecretServiceVaultPath:
    """Test SecretService when Vault is configured."""

    @pytest.mark.asyncio
    async def test_upsert_sensitive_vars_uses_vault(self):
        """When Vault configured, upsert_sensitive_vars writes to Vault + creates ExternalSecret."""
        from app.services.secret_service import SecretService

        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.custom_objects = MagicMock()

        svc = SecretService(k8s)
        mock_vault = MagicMock()
        mock_vault.is_configured.return_value = True
        mock_vault.write_secrets = AsyncMock()
        svc._vault = mock_vault

        result = await svc.upsert_sensitive_vars(
            namespace="tenant-rotterdam",
            app_slug="my-api",
            tenant_slug="rotterdam",
            data={"DB_PASSWORD": "secret123"},
        )
        assert result is True
        mock_vault.write_secrets.assert_called_once_with("rotterdam", "my-api", {"DB_PASSWORD": "secret123"})
        k8s.custom_objects.create_namespaced_custom_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_sensitive_vars_fallback_to_k8s(self):
        """When Vault NOT configured, falls back to K8s Secret."""
        from app.services.secret_service import SecretService

        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.core_v1 = MagicMock()

        svc = SecretService(k8s)
        mock_vault = MagicMock()
        mock_vault.is_configured.return_value = False
        svc._vault = mock_vault

        result = await svc.upsert_sensitive_vars(
            namespace="tenant-test",
            app_slug="app1",
            tenant_slug="test",
            data={"KEY": "val"},
        )
        assert result is True
        # Should call K8s directly, not Vault
        mock_vault.write_secrets.assert_not_called()
        k8s.core_v1.create_namespaced_secret.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_sensitive_vars_uses_vault(self):
        """When Vault configured, delete_sensitive_vars deletes from Vault + removes ExternalSecret."""
        from app.services.secret_service import SecretService

        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.custom_objects = MagicMock()

        svc = SecretService(k8s)
        mock_vault = MagicMock()
        mock_vault.is_configured.return_value = True
        mock_vault.delete_secrets = AsyncMock()
        svc._vault = mock_vault

        result = await svc.delete_sensitive_vars(
            namespace="tenant-rotterdam",
            app_slug="my-api",
            tenant_slug="rotterdam",
        )
        assert result is True
        mock_vault.delete_secrets.assert_called_once()
        k8s.custom_objects.delete_namespaced_custom_object.assert_called_once()

    def test_uses_vault_true(self):
        from app.services.secret_service import SecretService

        k8s = MagicMock()
        svc = SecretService(k8s)
        mock_vault = MagicMock()
        mock_vault.is_configured.return_value = True
        svc._vault = mock_vault
        assert svc.uses_vault() is True

    def test_uses_vault_false(self):
        from app.services.secret_service import SecretService

        k8s = MagicMock()
        svc = SecretService(k8s)
        mock_vault = MagicMock()
        mock_vault.is_configured.return_value = False
        svc._vault = mock_vault
        assert svc.uses_vault() is False

    @pytest.mark.asyncio
    async def test_ensure_external_secret_handles_409(self):
        """ExternalSecret creation handles 409 conflict (update instead)."""
        from kubernetes.client.exceptions import ApiException

        from app.services.secret_service import SecretService

        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.custom_objects = MagicMock()
        k8s.custom_objects.create_namespaced_custom_object.side_effect = ApiException(status=409)

        svc = SecretService(k8s)
        svc._ensure_external_secret("tenant-test", "my-app", "test")

        k8s.custom_objects.replace_namespaced_custom_object.assert_called_once()


# ---------------------------------------------------------------------------
# PUT /secrets and GET /secrets API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_secrets_endpoint_vault_path(async_client, db_session):
    """PUT /apps/{slug}/secrets writes to Vault when configured."""
    import uuid

    from app.models.application import Application
    from app.models.tenant import Tenant

    tenant = Tenant(
        id=uuid.uuid4(),
        slug="vault-tenant",
        name="Vault Test",
        namespace="tenant-vault-tenant",
        keycloak_realm="vault-tenant",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db_session.add(tenant)
    from app.models.tenant_member import MemberRole, TenantMember

    from app.models.tenant_member import MemberRole as _MR, TenantMember as _TM
    db_session.add(_TM(id=uuid.uuid4(), tenant_id=tenant.id, user_id="test-user", email="test@t.nl", role=_MR("owner")))
    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="vault-app",
        name="Vault App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    with patch("app.services.secret_service.SecretService") as MockSvc:
        mock_instance = MagicMock()
        mock_instance.upsert_sensitive_vars = AsyncMock(return_value=True)
        mock_instance.uses_vault.return_value = True
        MockSvc.return_value = mock_instance

        resp = await async_client.put(
            f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/secrets",
            json={"secrets": {"DB_PASSWORD": "test123", "API_KEY": "abc"}},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert sorted(data["keys"]) == ["API_KEY", "DB_PASSWORD"]


@pytest.mark.asyncio
async def test_get_secrets_endpoint_lists_keys(async_client, db_session):
    """GET /apps/{slug}/secrets returns key list (no values)."""
    import uuid

    from app.models.application import Application
    from app.models.tenant import Tenant

    tenant = Tenant(
        id=uuid.uuid4(),
        slug="keys-tenant",
        name="Keys Test",
        namespace="tenant-keys-tenant",
        keycloak_realm="keys-tenant",
        cpu_limit="4",
        memory_limit="8Gi",
        storage_limit="50Gi",
    )
    db_session.add(tenant)
    from app.models.tenant_member import MemberRole as _MR, TenantMember as _TM
    db_session.add(_TM(id=uuid.uuid4(), tenant_id=tenant.id, user_id="test-user", email="test@t.nl", role=_MR("owner")))
    app_obj = Application(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        slug="keys-app",
        name="Keys App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    with (
        patch("app.services.secret_service.SecretService") as MockSvc,
        patch("app.services.vault_service.vault_service") as mock_vault,
    ):
        mock_instance = MagicMock()
        mock_instance.uses_vault.return_value = True
        MockSvc.return_value = mock_instance
        mock_vault.list_keys = AsyncMock(return_value=["DB_PASSWORD", "API_KEY"])

        resp = await async_client.get(
            f"/api/v1/tenants/{tenant.slug}/apps/{app_obj.slug}/secrets",
        )

    assert resp.status_code == 200
    data = resp.json()
    assert sorted(data["keys"]) == ["API_KEY", "DB_PASSWORD"]
