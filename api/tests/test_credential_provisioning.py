"""Tests for Everest credential provisioning and background loop."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType
from app.services.everest_client import EverestClient
from app.services.managed_service import ManagedServiceProvisioner


def _make_service(
    name: str = "test-db",
    stype: ServiceType = ServiceType.POSTGRES,
    tier: ServiceTier = ServiceTier.DEV,
) -> ManagedService:
    """Create a transient ManagedService object."""
    svc = ManagedService(
        name=name,
        service_type=stype,
        tier=tier,
        status=ServiceStatus.PROVISIONING,
    )
    svc.secret_name = None
    svc.service_namespace = None
    svc.connection_hint = None
    svc.everest_name = None
    svc.db_name = None
    svc.db_user = None
    svc.credentials_provisioned = False
    return svc


def _mock_k8s_with_admin_secret(data: dict[str, str]) -> MagicMock:
    """Return a mock K8s client with admin secret data."""
    mock_k8s = MagicMock()
    mock_k8s.is_available.return_value = True
    mock_secret = MagicMock()
    mock_secret.data = {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}
    mock_k8s.core_v1.read_namespaced_secret.return_value = mock_secret
    mock_k8s.core_v1.create_namespaced_secret.return_value = MagicMock()
    return mock_k8s


# ---------------------------------------------------------------------------
# _provision_everest_credentials (via sync_details)
# ---------------------------------------------------------------------------


class TestProvisionEverestCredentials:
    """Test that sync_details triggers credential provisioning for Everest DBs."""

    @pytest.mark.asyncio
    async def test_pg_credentials_provisioned_on_ready(self):
        """When PG status=ready, must copy admin creds to tenant secret (PgBouncer limitation)."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_details.return_value = {"status": "ready"}

        k8s = _mock_k8s_with_admin_secret({
            "user": "postgres", "password": "adminpass",
            "host": "mydb-ha.everest.svc", "port": "5432",
        })

        svc = _make_service(name="app-pg", stype=ServiceType.POSTGRES)
        svc.everest_name = "acme-app-pg"
        svc.service_namespace = "everest"
        svc.status = ServiceStatus.PROVISIONING

        p = ManagedServiceProvisioner(k8s, everest=everest)
        await p.sync_details(svc, tenant_namespace="tenant-acme")

        assert svc.status == ServiceStatus.READY
        assert svc.credentials_provisioned is True
        assert svc.secret_name == "svc-app-pg"
        # PG copies admin creds (no custom user due to PgBouncer)
        k8s.core_v1.create_namespaced_secret.assert_called_once()
        call_args = k8s.core_v1.create_namespaced_secret.call_args
        assert call_args[0][0] == "tenant-acme"

    @pytest.mark.asyncio
    async def test_mysql_credentials_provisioned_on_ready(self):
        """When MySQL status=ready, must create custom user/db and tenant secret."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_details.return_value = {"status": "ready"}

        k8s = _mock_k8s_with_admin_secret({
            "user": "root", "password": "adminpass",
            "host": "mydb-haproxy.everest.svc", "port": "3306",
        })

        svc = _make_service(name="app-mysql", stype=ServiceType.MYSQL)
        svc.everest_name = "acme-app-mysql"
        svc.service_namespace = "everest"
        svc.status = ServiceStatus.PROVISIONING

        mock_conn = MagicMock()
        mock_cursor = AsyncMock()
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.close = MagicMock()

        p = ManagedServiceProvisioner(k8s, everest=everest)
        with patch("aiomysql.connect", new_callable=AsyncMock, return_value=mock_conn):
            await p.sync_details(svc, tenant_namespace="tenant-acme")

        assert svc.status == ServiceStatus.READY
        assert svc.credentials_provisioned is True
        assert svc.secret_name == "svc-app-mysql"
        assert svc.connection_hint is not None
        assert "mysql://" in svc.connection_hint

    @pytest.mark.asyncio
    async def test_mongodb_credentials_provisioned_on_ready(self):
        """When MongoDB status=ready, must create custom user/db and tenant secret."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_details.return_value = {"status": "ready"}

        k8s = _mock_k8s_with_admin_secret({
            "user": "databaseAdmin", "password": "adminpass",
            "host": "mydb-mongos.everest.svc", "port": "27017",
        })

        svc = _make_service(name="app-mongo", stype=ServiceType.MONGODB)
        svc.everest_name = "acme-app-mongo"
        svc.service_namespace = "everest"
        svc.status = ServiceStatus.PROVISIONING

        mock_db = AsyncMock()
        mock_db.command = AsyncMock(side_effect=[{"users": []}, None])
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_client.close = MagicMock()

        p = ManagedServiceProvisioner(k8s, everest=everest)
        with patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=mock_client):
            await p.sync_details(svc, tenant_namespace="tenant-acme")

        assert svc.status == ServiceStatus.READY
        assert svc.credentials_provisioned is True
        assert svc.secret_name == "svc-app-mongo"
        assert "mongodb://" in svc.connection_hint

    @pytest.mark.asyncio
    async def test_no_provision_when_already_provisioned(self):
        """If credentials_provisioned=True, must NOT re-provision."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_details.return_value = {"status": "ready"}

        k8s = MagicMock()
        k8s.is_available.return_value = True

        svc = _make_service(name="app-pg", stype=ServiceType.POSTGRES)
        svc.everest_name = "acme-app-pg"
        svc.service_namespace = "everest"
        svc.status = ServiceStatus.READY
        svc.credentials_provisioned = True  # Already done

        p = ManagedServiceProvisioner(k8s, everest=everest)
        await p.sync_details(svc, tenant_namespace="tenant-acme")

        # Should NOT touch K8s secrets
        k8s.core_v1.read_namespaced_secret.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_provision_without_tenant_namespace(self):
        """If tenant_namespace is empty, must NOT attempt provisioning."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_details.return_value = {"status": "ready"}

        k8s = MagicMock()
        k8s.is_available.return_value = True

        svc = _make_service(name="app-pg", stype=ServiceType.POSTGRES)
        svc.everest_name = "acme-app-pg"
        svc.service_namespace = "everest"

        p = ManagedServiceProvisioner(k8s, everest=everest)
        await p.sync_details(svc)  # No tenant_namespace

        assert svc.status == ServiceStatus.READY
        assert svc.credentials_provisioned is False

    @pytest.mark.asyncio
    async def test_provision_failure_does_not_crash(self):
        """If credential provisioning fails, must log error but not crash."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_details.return_value = {"status": "ready"}

        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.core_v1.read_namespaced_secret.side_effect = Exception("K8s unreachable")

        svc = _make_service(name="app-pg", stype=ServiceType.POSTGRES)
        svc.everest_name = "acme-app-pg"
        svc.service_namespace = "everest"

        p = ManagedServiceProvisioner(k8s, everest=everest)
        # Should not raise
        await p.sync_details(svc, tenant_namespace="tenant-acme")

        assert svc.status == ServiceStatus.READY
        assert svc.credentials_provisioned is False  # Failed, not set

    @pytest.mark.asyncio
    async def test_no_provision_when_not_ready(self):
        """Credentials must only be provisioned when status is READY."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.get_database_details.return_value = {"status": "initializing"}

        k8s = MagicMock()
        k8s.is_available.return_value = True

        svc = _make_service(name="app-pg", stype=ServiceType.POSTGRES)
        svc.everest_name = "acme-app-pg"
        svc.service_namespace = "everest"

        p = ManagedServiceProvisioner(k8s, everest=everest)
        await p.sync_details(svc, tenant_namespace="tenant-acme")

        assert svc.status == ServiceStatus.PROVISIONING
        assert svc.credentials_provisioned is False


# ---------------------------------------------------------------------------
# Everest provision namespace verification
# ---------------------------------------------------------------------------


class TestEverestNamespaceRevert:
    """Verify that Everest provisions use the shared 'everest' namespace."""

    @pytest.mark.asyncio
    async def test_provision_uses_everest_namespace(self):
        """_everest_provision must create DB in 'everest' namespace, not tenant."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.return_value = {"metadata": {"name": "acme-test-db"}}

        k8s = MagicMock()
        k8s.is_available.return_value = True

        svc = _make_service(stype=ServiceType.POSTGRES)
        p = ManagedServiceProvisioner(k8s, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        # Must call Everest with namespace="everest", NOT "tenant-acme"
        everest.create_database.assert_called_once_with(
            name="acme-test-db", engine_type="postgres", tier="dev", namespace="everest"
        )
        assert svc.service_namespace == "everest"

    @pytest.mark.asyncio
    async def test_provision_mysql_uses_everest_namespace(self):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.return_value = {}

        k8s = MagicMock()
        k8s.is_available.return_value = True

        svc = _make_service(stype=ServiceType.MYSQL)
        p = ManagedServiceProvisioner(k8s, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        everest.create_database.assert_called_once_with(
            name="acme-test-db", engine_type="mysql", tier="dev", namespace="everest"
        )
        assert svc.service_namespace == "everest"

    @pytest.mark.asyncio
    async def test_provision_mongodb_uses_everest_namespace(self):
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.return_value = {}

        k8s = MagicMock()
        k8s.is_available.return_value = True

        svc = _make_service(stype=ServiceType.MONGODB)
        p = ManagedServiceProvisioner(k8s, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        everest.create_database.assert_called_once_with(
            name="acme-test-db", engine_type="mongodb", tier="dev", namespace="everest"
        )
        assert svc.service_namespace == "everest"

    @pytest.mark.asyncio
    async def test_crd_fallback_still_uses_tenant_namespace(self):
        """When Everest fails, CRD fallback must use tenant namespace."""
        everest = AsyncMock(spec=EverestClient)
        everest.is_configured.return_value = True
        everest.create_database.side_effect = Exception("Everest down")

        k8s = MagicMock()
        k8s.is_available.return_value = True
        k8s.custom_objects = MagicMock()

        svc = _make_service(stype=ServiceType.POSTGRES)
        p = ManagedServiceProvisioner(k8s, everest=everest)
        await p.provision(svc, "tenant-acme", tenant_slug="acme")

        assert svc.service_namespace == "tenant-acme"


# ---------------------------------------------------------------------------
# Background credential provisioning loop
# ---------------------------------------------------------------------------


class TestCredentialProvisioningTick:
    """Test the _credential_provisioning_tick function (single iteration of background loop)."""

    @pytest.mark.asyncio
    async def test_tick_processes_provisioning_and_ready_services(self):
        """Tick must find PROVISIONING and READY+not-provisioned services."""
        from app.main import _credential_provisioning_tick

        mock_svc = MagicMock(spec=ManagedService)
        mock_svc.status = ServiceStatus.PROVISIONING
        mock_svc.credentials_provisioned = False
        mock_svc.tenant_id = "tenant-123"

        mock_tenant = MagicMock()
        mock_tenant.namespace = "tenant-acme"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_svc]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.get = AsyncMock(return_value=mock_tenant)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.managed_service.ManagedServiceProvisioner") as MockProvisioner:
            mock_provisioner_instance = AsyncMock()
            MockProvisioner.return_value = mock_provisioner_instance

            count = await _credential_provisioning_tick(mock_factory)

        assert count == 1
        mock_provisioner_instance.sync_details.assert_called_once_with(
            mock_svc, tenant_namespace="tenant-acme"
        )
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_returns_zero_when_no_services(self):
        """Tick must return 0 when no services need provisioning."""
        from app.main import _credential_provisioning_tick

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        count = await _credential_provisioning_tick(mock_factory)

        assert count == 0
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_tick_skips_tenant_without_namespace(self):
        """If tenant has no namespace, skip that service."""
        from app.main import _credential_provisioning_tick

        mock_svc = MagicMock(spec=ManagedService)
        mock_svc.status = ServiceStatus.READY
        mock_svc.credentials_provisioned = False
        mock_svc.tenant_id = "tenant-123"

        mock_tenant = MagicMock()
        mock_tenant.namespace = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_svc]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.get = AsyncMock(return_value=mock_tenant)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.managed_service.ManagedServiceProvisioner") as MockProvisioner:
            mock_provisioner_instance = AsyncMock()
            MockProvisioner.return_value = mock_provisioner_instance

            count = await _credential_provisioning_tick(mock_factory)

        assert count == 1  # Still counted, but sync_details not called
        mock_provisioner_instance.sync_details.assert_not_called()

    @pytest.mark.asyncio
    async def test_tick_propagates_exceptions(self):
        """Tick must propagate exceptions (loop handles them)."""
        from app.main import _credential_provisioning_tick

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(Exception, match="DB down"):
            await _credential_provisioning_tick(mock_factory)
