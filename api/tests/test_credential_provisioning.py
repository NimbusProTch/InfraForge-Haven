"""Tests for Everest credential provisioning and background loop."""

import base64
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.managed_service import ManagedService, ServiceStatus, ServiceTier, ServiceType
from app.models.tenant import Tenant
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

        k8s = _mock_k8s_with_admin_secret(
            {
                "user": "postgres",
                "password": "adminpass",
                "host": "mydb-ha.everest.svc",
                "port": "5432",
            }
        )

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

        k8s = _mock_k8s_with_admin_secret(
            {
                "user": "root",
                "password": "adminpass",
                "host": "mydb-haproxy.everest.svc",
                "port": "3306",
            }
        )

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

        k8s = _mock_k8s_with_admin_secret(
            {
                "user": "databaseAdmin",
                "password": "adminpass",
                "host": "mydb-mongos.everest.svc",
                "port": "27017",
            }
        )

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

    def _mock_factory(self, query_result, get_results=None):
        """Build a mock session factory that supports multiple context manager entries."""

        call_count = 0

        def make_session():
            nonlocal call_count
            call_count += 1
            session = AsyncMock()

            if call_count == 1:
                # First session: query for service IDs
                mock_result = MagicMock()
                mock_result.all.return_value = query_result
                session.execute = AsyncMock(return_value=mock_result)
            else:
                # Subsequent sessions: per-service processing
                if get_results:
                    session.get = AsyncMock(side_effect=lambda model, id: get_results.get((model, id)))
                else:
                    session.get = AsyncMock(return_value=None)
                session.commit = AsyncMock()

            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        factory = MagicMock(side_effect=make_session)
        return factory

    @pytest.mark.asyncio
    async def test_tick_processes_services_independently(self):
        """Each service gets its own session and commit."""
        from app.main import _credential_provisioning_tick

        svc_id = "svc-123"
        mock_svc = MagicMock(spec=ManagedService)
        mock_svc.tenant_id = "tenant-123"

        mock_tenant = MagicMock()
        mock_tenant.namespace = "tenant-acme"

        factory = self._mock_factory(
            query_result=[(svc_id,)],
            get_results={(ManagedService, svc_id): mock_svc, (Tenant, "tenant-123"): mock_tenant},
        )

        with patch("app.services.managed_service.ManagedServiceProvisioner") as MockP:
            MockP.return_value = AsyncMock()
            count = await _credential_provisioning_tick(factory)

        assert count == 1
        MockP.return_value.sync_details.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_returns_zero_when_no_services(self):
        """Tick must return 0 when no services need provisioning."""
        from app.main import _credential_provisioning_tick

        factory = self._mock_factory(query_result=[])
        count = await _credential_provisioning_tick(factory)
        assert count == 0

    @pytest.mark.asyncio
    async def test_tick_one_failure_doesnt_block_others(self):
        """If one service fails, others should still be processed."""
        from app.main import _credential_provisioning_tick

        svc_id1 = "svc-fail"
        svc_id2 = "svc-ok"

        mock_svc1 = MagicMock(spec=ManagedService)
        mock_svc1.tenant_id = "t1"
        mock_svc2 = MagicMock(spec=ManagedService)
        mock_svc2.tenant_id = "t2"

        mock_tenant = MagicMock()
        mock_tenant.namespace = "tenant-test"

        call_count = [0]

        def make_session():
            call_count[0] += 1
            session = AsyncMock()

            if call_count[0] == 1:
                # Query session
                mock_result = MagicMock()
                mock_result.all.return_value = [(svc_id1,), (svc_id2,)]
                session.execute = AsyncMock(return_value=mock_result)
            elif call_count[0] == 2:
                # First service session — will fail
                session.get = AsyncMock(side_effect=Exception("DB error"))
            else:
                # Second service session — should succeed
                session.get = AsyncMock(side_effect=lambda m, id: mock_svc2 if m == ManagedService else mock_tenant)
                session.commit = AsyncMock()

            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        factory = MagicMock(side_effect=make_session)

        with patch("app.services.managed_service.ManagedServiceProvisioner") as MockP:
            MockP.return_value = AsyncMock()
            count = await _credential_provisioning_tick(factory)

        # First failed, second succeeded
        assert count == 1

    @pytest.mark.asyncio
    async def test_tick_query_failure_propagates(self):
        """If initial query fails, exception propagates."""
        from app.main import _credential_provisioning_tick

        factory = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory.return_value = ctx

        with pytest.raises(Exception, match="DB down"):
            await _credential_provisioning_tick(factory)

    @pytest.mark.asyncio
    async def test_tick_timeout_marks_stuck_service_failed(self):
        """Service stuck in PROVISIONING for >10min must be marked FAILED.

        Updated 2026-04-18: `_credential_provisioning_tick` now calls
        `sync_details` BEFORE the age-based timeout check (so services that
        finished provisioning late get promoted to READY instead of stamped
        FAILED). Mock the provisioner's sync_details as a no-op AsyncMock —
        status stays PROVISIONING, timeout check then stamps FAILED.
        """
        from datetime import datetime, timedelta

        from app.main import _credential_provisioning_tick

        svc_id = "svc-timeout"
        mock_svc = MagicMock(spec=ManagedService)
        mock_svc.name = "stuck-pg"
        mock_svc.status = ServiceStatus.PROVISIONING
        mock_svc.credentials_provisioned = False
        # Created 25 minutes ago — exceeds the 20min provision timeout
        mock_svc.created_at = datetime.now(UTC) - timedelta(minutes=25)

        # Tenant mock for sync_details lookup
        mock_tenant = MagicMock()
        mock_tenant.namespace = "tenant-stuck"

        call_count = [0]

        def get_by_model(model_cls, _id):
            if model_cls.__name__ == "Tenant":
                return mock_tenant
            return mock_svc

        def make_session():
            call_count[0] += 1
            session = AsyncMock()
            if call_count[0] == 1:
                mock_result = MagicMock()
                mock_result.all.return_value = [(svc_id,)]
                session.execute = AsyncMock(return_value=mock_result)
            else:
                session.get = AsyncMock(side_effect=get_by_model)
                session.commit = AsyncMock()
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        factory = MagicMock(side_effect=make_session)

        # Provisioner must be a proper AsyncMock now that sync_details is
        # called FIRST (see fix/service-timeout-sync-order). Without this
        # patch, `await provisioner.sync_details(...)` raises TypeError on
        # the default MagicMock return value.
        mock_provisioner_class = MagicMock()
        mock_provisioner_instance = MagicMock()
        mock_provisioner_instance.sync_details = AsyncMock(return_value=None)
        mock_provisioner_class.return_value = mock_provisioner_instance

        with patch("app.services.managed_service.ManagedServiceProvisioner", mock_provisioner_class):
            count = await _credential_provisioning_tick(factory)

        assert count == 1
        assert mock_svc.status == ServiceStatus.FAILED
        assert "timed out" in mock_svc.error_message.lower()
