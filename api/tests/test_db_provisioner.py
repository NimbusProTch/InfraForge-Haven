"""Tests for db_provisioner — custom user/db creation + tenant secret management."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.db_provisioner import (
    create_custom_database,
    create_tenant_secret,
    delete_tenant_secret,
    generate_password,
    read_admin_credentials,
    tenant_secret_name,
)

# ---------------------------------------------------------------------------
# generate_password
# ---------------------------------------------------------------------------


def test_generate_password_default_length():
    pwd = generate_password()
    assert len(pwd) == 24


def test_generate_password_custom_length():
    pwd = generate_password(32)
    assert len(pwd) == 32


def test_generate_password_url_safe():
    """Password must not contain special chars that break URLs."""
    pwd = generate_password(100)
    assert all(c.isalnum() for c in pwd)


def test_generate_password_unique():
    passwords = {generate_password() for _ in range(50)}
    assert len(passwords) == 50


# ---------------------------------------------------------------------------
# tenant_secret_name
# ---------------------------------------------------------------------------


def test_tenant_secret_name():
    assert tenant_secret_name("app-pg") == "svc-app-pg"
    assert tenant_secret_name("my-redis") == "svc-my-redis"


# ---------------------------------------------------------------------------
# read_admin_credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_admin_credentials():
    """Must decode base64 secret data."""
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_secret = MagicMock()
    mock_secret.data = {
        "user": base64.b64encode(b"postgres").decode(),
        "password": base64.b64encode(b"secret123").decode(),
        "host": base64.b64encode(b"pg-ha.everest.svc").decode(),
        "port": base64.b64encode(b"5432").decode(),
    }
    mock_k8s.core_v1.read_namespaced_secret.return_value = mock_secret

    creds = await read_admin_credentials(mock_k8s, "everest-secrets-test-pg")

    assert creds["user"] == "postgres"
    assert creds["password"] == "secret123"
    assert creds["host"] == "pg-ha.everest.svc"
    mock_k8s.core_v1.read_namespaced_secret.assert_called_once_with(
        name="everest-secrets-test-pg", namespace="everest"
    )


@pytest.mark.asyncio
async def test_read_admin_credentials_raises_when_k8s_unavailable():
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = False

    with pytest.raises(RuntimeError, match="K8s client not available"):
        await read_admin_credentials(mock_k8s, "test")


# ---------------------------------------------------------------------------
# create_custom_database
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_custom_database_creates_db_and_user():
    """Must run CREATE DATABASE, CREATE USER, GRANT ALL."""
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_secret = MagicMock()
    mock_secret.data = {
        "user": base64.b64encode(b"postgres").decode(),
        "password": base64.b64encode(b"adminpass").decode(),
        "host": base64.b64encode(b"mydb-ha.everest.svc").decode(),
        "port": base64.b64encode(b"5432").decode(),
    }
    mock_k8s.core_v1.read_namespaced_secret.return_value = mock_secret

    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=None)  # DB and user don't exist
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()

    mock_db_conn = AsyncMock()
    mock_db_conn.execute = AsyncMock()
    mock_db_conn.close = AsyncMock()

    call_count = 0

    async def mock_connect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_conn  # admin connection
        return mock_db_conn  # db-specific connection for GRANT

    with patch("app.services.db_provisioner.asyncpg.connect", side_effect=mock_connect):
        result = await create_custom_database(
            k8s=mock_k8s,
            everest_secret_name="everest-secrets-test-pg",
            db_name="myapp_db",
            db_user="myapp_user",
            db_password="custom_pass",
        )

    assert result["DATABASE_URL"] == "postgresql://myapp_user:custom_pass@mydb-ha.everest.svc:5432/myapp_db"
    assert result["DB_HOST"] == "mydb-ha.everest.svc"
    assert result["DB_PORT"] == "5432"
    assert result["DB_USER"] == "myapp_user"
    assert result["DB_PASSWORD"] == "custom_pass"
    assert result["DB_NAME"] == "myapp_db"

    # Verify SQL was executed
    execute_calls = [str(c) for c in mock_conn.execute.call_args_list]
    assert any("CREATE DATABASE" in c for c in execute_calls)
    assert any("CREATE USER" in c for c in execute_calls)
    assert any("GRANT ALL" in c for c in execute_calls)


@pytest.mark.asyncio
async def test_create_custom_database_no_db_name_uses_postgres():
    """When db_name is None, should use 'postgres' default and skip CREATE DATABASE."""
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_secret = MagicMock()
    mock_secret.data = {
        "user": base64.b64encode(b"postgres").decode(),
        "password": base64.b64encode(b"adminpass").decode(),
        "host": base64.b64encode(b"mydb-ha.everest.svc").decode(),
        "port": base64.b64encode(b"5432").decode(),
    }
    mock_k8s.core_v1.read_namespaced_secret.return_value = mock_secret

    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()

    with patch("app.services.db_provisioner.asyncpg.connect", return_value=mock_conn):
        result = await create_custom_database(
            k8s=mock_k8s,
            everest_secret_name="everest-secrets-test-pg",
            db_name=None,
            db_user="myuser",
        )

    assert result["DB_NAME"] == "postgres"
    assert "myuser" in result["DATABASE_URL"]
    # CREATE DATABASE should NOT have been called
    execute_calls = [str(c) for c in mock_conn.execute.call_args_list]
    assert not any("CREATE DATABASE" in c for c in execute_calls)


@pytest.mark.asyncio
async def test_create_custom_database_auto_generates_password():
    """When db_password is None, must auto-generate."""
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_secret = MagicMock()
    mock_secret.data = {
        "user": base64.b64encode(b"postgres").decode(),
        "password": base64.b64encode(b"adminpass").decode(),
        "host": base64.b64encode(b"db-ha.everest.svc").decode(),
        "port": base64.b64encode(b"5432").decode(),
    }
    mock_k8s.core_v1.read_namespaced_secret.return_value = mock_secret

    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()

    mock_db_conn = AsyncMock()
    mock_db_conn.execute = AsyncMock()
    mock_db_conn.close = AsyncMock()

    conns = [mock_conn, mock_db_conn]

    async def mock_connect(**kwargs):
        return conns.pop(0) if conns else mock_db_conn

    with patch("app.services.db_provisioner.asyncpg.connect", side_effect=mock_connect):
        result = await create_custom_database(
            k8s=mock_k8s,
            everest_secret_name="everest-secrets-test-pg",
            db_name="testdb",
            db_user="testuser",
            db_password=None,
        )

    assert len(result["DB_PASSWORD"]) == 24
    assert result["DB_PASSWORD"].isalnum()


@pytest.mark.asyncio
async def test_create_custom_database_host_rewrite():
    """Must replace -primary.everest.svc with -ha.everest.svc."""
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_secret = MagicMock()
    mock_secret.data = {
        "user": base64.b64encode(b"postgres").decode(),
        "password": base64.b64encode(b"pass").decode(),
        "host": base64.b64encode(b"mydb-primary.everest.svc").decode(),
        "port": base64.b64encode(b"5432").decode(),
    }
    mock_k8s.core_v1.read_namespaced_secret.return_value = mock_secret

    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()

    with patch("app.services.db_provisioner.asyncpg.connect", return_value=mock_conn):
        result = await create_custom_database(
            k8s=mock_k8s,
            everest_secret_name="test",
            db_name=None,
            db_user="u",
            db_password="p",
        )

    assert "mydb-ha.everest.svc" in result["DB_HOST"]
    assert "-primary" not in result["DB_HOST"]


# ---------------------------------------------------------------------------
# create_tenant_secret
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tenant_secret_creates_new():
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_k8s.core_v1.create_namespaced_secret.return_value = MagicMock()

    await create_tenant_secret(
        mock_k8s, "tenant-amsterdam", "svc-app-pg", {"DATABASE_URL": "postgresql://..."}
    )

    mock_k8s.core_v1.create_namespaced_secret.assert_called_once()
    call_args = mock_k8s.core_v1.create_namespaced_secret.call_args
    assert call_args[0][0] == "tenant-amsterdam"
    secret = call_args[0][1]
    assert secret.metadata.name == "svc-app-pg"
    assert secret.metadata.namespace == "tenant-amsterdam"


@pytest.mark.asyncio
async def test_create_tenant_secret_updates_existing():
    """Must replace if 409 Conflict."""
    from kubernetes.client import ApiException

    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_k8s.core_v1.create_namespaced_secret.side_effect = ApiException(status=409)
    mock_k8s.core_v1.replace_namespaced_secret.return_value = MagicMock()

    await create_tenant_secret(
        mock_k8s, "tenant-amsterdam", "svc-app-pg", {"DATABASE_URL": "postgresql://..."}
    )

    mock_k8s.core_v1.replace_namespaced_secret.assert_called_once()


# ---------------------------------------------------------------------------
# delete_tenant_secret
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_tenant_secret():
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_k8s.core_v1.delete_namespaced_secret.return_value = MagicMock()

    await delete_tenant_secret(mock_k8s, "tenant-amsterdam", "svc-app-pg")
    mock_k8s.core_v1.delete_namespaced_secret.assert_called_once_with("svc-app-pg", "tenant-amsterdam")


@pytest.mark.asyncio
async def test_delete_tenant_secret_ignores_404():
    from kubernetes.client import ApiException

    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_k8s.core_v1.delete_namespaced_secret.side_effect = ApiException(status=404)

    # Should not raise
    await delete_tenant_secret(mock_k8s, "tenant-amsterdam", "svc-app-pg")
