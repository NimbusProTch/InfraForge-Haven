"""Tests for the lifecycle event bus and SSE streaming.

Covers:
  - LifecycleChannel: emit, mark_done, events_since, stream
  - LifecycleEventBus: channel management, emit, cleanup
  - LifecycleEvent: to_sse serialization
  - SSE endpoints: tenant, service, app events
  - Integration: tenant provision emits events
  - Integration: service provision emits events
  - Integration: tenant deprovision emits events
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.main import app
from app.models.base import Base
from app.models.cluster import Cluster  # noqa: F401
from app.models.cronjob import CronJob  # noqa: F401
from app.models.tenant import Tenant
from app.models.tenant_member import MemberRole, TenantMember
from app.services.lifecycle_events import (
    LifecycleChannel,
    LifecycleEvent,
    LifecycleEventBus,
    _DoneEvent,
    lifecycle_bus,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def k8s_mock():
    k8s = MagicMock()
    k8s.is_available.return_value = True
    k8s.core_v1 = MagicMock()
    k8s.apps_v1 = MagicMock()
    k8s.rbac_v1 = MagicMock()
    k8s.custom_objects = MagicMock()
    k8s.custom_objects.create_namespaced_custom_object.return_value = {}
    k8s.custom_objects.delete_namespaced_custom_object.return_value = {}
    return k8s


@pytest_asyncio.fixture
async def client(db, k8s_mock):
    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_k8s] = lambda: k8s_mock
    app.dependency_overrides[verify_token] = lambda: {
        "sub": "test-user",
        "email": "test@haven.nl",
        "realm_access": {"roles": ["platform-admin"]},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


def _patch_externals():
    """H3a (P2.1): slots [0]/[1] kept as nullcontext to preserve positional
    indexing in callsites. The keycloak realm methods were deleted."""
    from contextlib import nullcontext

    return [
        nullcontext(),  # was: keycloak_service.create_realm (deleted in H3a)
        nullcontext(),  # was: keycloak_service.delete_realm (deleted in H3a)
        patch("app.routers.tenants.gitops_scaffold.scaffold_tenant", new_callable=AsyncMock),
        patch("app.routers.tenants.gitops_scaffold.delete_tenant", new_callable=AsyncMock),
        patch("app.routers.applications.gitops_scaffold.scaffold_app", new_callable=AsyncMock),
        patch("app.routers.applications.gitops_scaffold.delete_app", new_callable=AsyncMock),
        patch(
            "app.services.tenant_service.HarborService",
            return_value=MagicMock(
                create_project=AsyncMock(),
                delete_project=AsyncMock(),
                create_robot_account=AsyncMock(return_value={"name": "robot", "secret": "pass"}),
                build_imagepull_secret=MagicMock(
                    return_value={
                        "metadata": {"name": "harbor-registry-secret"},
                        "type": "kubernetes.io/dockerconfigjson",
                        "data": {".dockerconfigjson": "e30="},
                    }
                ),
            ),
        ),
    ]


# ===========================================================================
# TEST: LifecycleEvent serialization
# ===========================================================================


class TestLifecycleEvent:
    def test_to_sse_basic(self):
        event = LifecycleEvent(event_id=1, step="namespace", status="done", message="Created")
        sse = event.to_sse()
        assert "id: 1\n" in sse
        assert "event: step\n" in sse
        assert '"step": "namespace"' in sse
        assert '"status": "done"' in sse

    def test_to_sse_with_detail(self):
        event = LifecycleEvent(event_id=2, step="quota", status="done", message="Applied", detail={"cpu": "8"})
        sse = event.to_sse()
        data_line = [l for l in sse.split("\n") if l.startswith("data:")][0]
        data = json.loads(data_line.removeprefix("data: "))
        assert data["detail"]["cpu"] == "8"

    def test_done_event_to_sse(self):
        event = _DoneEvent(event_id=5, success=True, message="All done")
        sse = event.to_sse()
        assert "event: done\n" in sse
        assert '"success": true' in sse


# ===========================================================================
# TEST: LifecycleChannel
# ===========================================================================


class TestLifecycleChannel:
    def test_emit_increments_counter(self):
        ch = LifecycleChannel()
        e1 = ch.emit("step1", "done", "First")
        e2 = ch.emit("step2", "done", "Second")
        assert e1.event_id == 1
        assert e2.event_id == 2

    def test_events_since(self):
        ch = LifecycleChannel()
        ch.emit("a", "done", "A")
        ch.emit("b", "done", "B")
        ch.emit("c", "done", "C")
        since_1 = ch.events_since(1)
        assert len(since_1) == 2
        assert since_1[0].step == "b"

    def test_mark_done(self):
        ch = LifecycleChannel()
        ch.emit("x", "done", "X")
        ch.mark_done(success=True, message="OK")
        assert ch.is_done is True
        assert len(ch.events) == 2
        assert isinstance(ch.events[-1], _DoneEvent)

    def test_events_property(self):
        ch = LifecycleChannel()
        ch.emit("a", "running", "Start")
        ch.emit("a", "done", "End")
        assert len(ch.events) == 2

    @pytest.mark.asyncio
    async def test_stream_replays_buffered(self):
        ch = LifecycleChannel()
        ch.emit("a", "done", "A")
        ch.emit("b", "done", "B")
        ch.mark_done()

        chunks = []
        async for chunk in ch.stream():
            chunks.append(chunk)
        # 2 step events + 1 done event
        assert len(chunks) == 3
        assert "step" in chunks[0]

    @pytest.mark.asyncio
    async def test_stream_with_last_event_id(self):
        ch = LifecycleChannel()
        ch.emit("a", "done", "A")
        ch.emit("b", "done", "B")
        ch.emit("c", "done", "C")
        ch.mark_done()

        chunks = []
        async for chunk in ch.stream(last_event_id=2):
            chunks.append(chunk)
        # Only event 3 + done
        assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_stream_live_events(self):
        ch = LifecycleChannel()
        received = []

        async def consumer():
            async for chunk in ch.stream():
                received.append(chunk)
                if "event: done" in chunk:
                    break

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.05)

        ch.emit("step1", "running", "First")
        await asyncio.sleep(0.05)
        ch.mark_done()
        await asyncio.sleep(0.05)

        await asyncio.wait_for(task, timeout=2)
        assert len(received) == 2


# ===========================================================================
# TEST: LifecycleEventBus
# ===========================================================================


class TestLifecycleEventBus:
    def test_emit_creates_channel(self):
        bus = LifecycleEventBus()
        bus.emit("test:key", "step1", "done", "Hello")
        ch = bus.get("test:key")
        assert ch is not None
        assert len(ch.events) == 1

    def test_channel_reuse(self):
        bus = LifecycleEventBus()
        ch1 = bus.channel("key:a")
        ch2 = bus.channel("key:a")
        assert ch1 is ch2

    def test_mark_done(self):
        bus = LifecycleEventBus()
        bus.emit("key:b", "s", "done", "msg")
        bus.mark_done("key:b")
        assert bus.get("key:b").is_done

    def test_get_nonexistent(self):
        bus = LifecycleEventBus()
        assert bus.get("nonexistent") is None

    def test_cleanup_removes_old_done(self):
        bus = LifecycleEventBus()
        bus.emit("old", "s", "done", "msg")
        bus.mark_done("old")
        # Hack: set created_at to old time
        bus._channels["old"]._created_at -= 999
        removed = bus.cleanup(max_age_seconds=10)
        assert removed == 1
        assert bus.get("old") is None

    def test_cleanup_keeps_active(self):
        bus = LifecycleEventBus()
        bus.emit("active", "s", "running", "msg")
        removed = bus.cleanup(max_age_seconds=0)
        assert removed == 0  # not done, not cleaned


# ===========================================================================
# TEST: SSE Endpoints
# ===========================================================================


class TestSSEEndpoints:
    """Test SSE endpoints with pre-completed channels (no hanging streams).

    H0-11: Each endpoint now requires the caller to be a TenantMember of
    the tenant whose stream they're subscribing to. The shared `client`
    fixture authenticates as 'test-user', so each test must seed a Tenant
    + TenantMember row before opening the stream.
    """

    @staticmethod
    async def _seed(db, slug: str) -> None:
        import uuid as _uuid

        t = Tenant(
            id=_uuid.uuid4(),
            slug=slug,
            name=slug,
            namespace=f"tenant-{slug}",
            keycloak_realm=slug,
            cpu_limit="1",
            memory_limit="1Gi",
            storage_limit="10Gi",
        )
        db.add(t)
        await db.flush()
        db.add(
            TenantMember(
                tenant_id=t.id,
                user_id="test-user",
                email="test@haven.nl",
                role=MemberRole("owner"),
            )
        )
        await db.commit()

    @pytest.mark.asyncio
    async def test_tenant_events_endpoint_returns_sse(self, client, db):
        await self._seed(db, "sse-test-1")
        key = "tenant:sse-test-1"
        lifecycle_bus._channels.pop(key, None)
        lifecycle_bus.emit(key, "namespace", "done", "NS created")
        lifecycle_bus.mark_done(key)

        async with client.stream("GET", "/api/v1/tenants/sse-test-1/events") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]
            body = ""
            async for chunk in r.aiter_text():
                body += chunk
                if "event: done" in body:
                    break
        assert "namespace" in body
        assert "NS created" in body

    @pytest.mark.asyncio
    async def test_service_events_endpoint(self, client, db):
        await self._seed(db, "sse-test-2")
        key = "service:sse-test-2:my-pg"
        lifecycle_bus._channels.pop(key, None)
        lifecycle_bus.emit(key, "provision", "done", "PG created")
        lifecycle_bus.mark_done(key)

        async with client.stream("GET", "/api/v1/tenants/sse-test-2/services/my-pg/events") as r:
            assert r.status_code == 200
            body = ""
            async for chunk in r.aiter_text():
                body += chunk
                if "event: done" in body:
                    break
        assert "PG created" in body

    @pytest.mark.asyncio
    async def test_app_events_endpoint(self, client, db):
        await self._seed(db, "sse-test-3")
        key = "app:sse-test-3:my-app"
        lifecycle_bus._channels.pop(key, None)
        lifecycle_bus.emit(key, "build", "done", "Build OK")
        lifecycle_bus.mark_done(key)

        async with client.stream("GET", "/api/v1/tenants/sse-test-3/apps/my-app/lifecycle-events") as r:
            assert r.status_code == 200
            body = ""
            async for chunk in r.aiter_text():
                body += chunk
                if "event: done" in body:
                    break
        assert "Build OK" in body

    @pytest.mark.asyncio
    async def test_events_contain_valid_sse_format(self, client, db):
        await self._seed(db, "sse-fmt")
        key = "tenant:sse-fmt"
        lifecycle_bus._channels.pop(key, None)
        lifecycle_bus.emit(key, "step1", "done", "msg1")
        lifecycle_bus.emit(key, "step2", "done", "msg2")
        lifecycle_bus.mark_done(key)

        async with client.stream("GET", "/api/v1/tenants/sse-fmt/events") as r:
            body = ""
            async for chunk in r.aiter_text():
                body += chunk
                if "event: done" in body:
                    break

        lines = body.strip().split("\n")
        id_lines = [l for l in lines if l.startswith("id:")]
        event_lines = [l for l in lines if l.startswith("event:")]
        data_lines = [l for l in lines if l.startswith("data:")]
        assert len(id_lines) == 3  # 2 steps + 1 done
        assert len(event_lines) == 3
        assert len(data_lines) == 3

        for dl in data_lines:
            parsed = json.loads(dl.removeprefix("data: "))
            assert isinstance(parsed, dict)


# ===========================================================================
# TEST: Integration — tenant provision emits lifecycle events
# ===========================================================================


class TestTenantProvisionEvents:
    @pytest.mark.asyncio
    async def test_provision_emits_all_steps(self, client, k8s_mock):
        # Clear any leftover
        lifecycle_bus._channels.pop("tenant:event-test", None)

        with (
            _patch_externals()[0],
            _patch_externals()[1],
            _patch_externals()[2],
            _patch_externals()[3],
            _patch_externals()[4],
            _patch_externals()[5],
            _patch_externals()[6],
        ):
            r = await client.post(
                "/api/v1/tenants",
                json={
                    "slug": "event-test",
                    "name": "Event Test Tenant",
                    "tier": "starter",
                    "cpu_limit": "4",
                    "memory_limit": "8Gi",
                    "storage_limit": "50Gi",
                },
            )
        assert r.status_code == 201

        ch = lifecycle_bus.get("tenant:event-test")
        assert ch is not None
        assert ch.is_done

        events = ch.events
        step_events = [e for e in events if isinstance(e, LifecycleEvent)]
        done_events = [e for e in events if isinstance(e, _DoneEvent)]

        # Expected steps: namespace, quota, limits, network, rbac, harbor-secret, harbor-project, appset
        # Each has running + done = 16 step events
        step_names = {e.step for e in step_events}
        assert "namespace" in step_names
        assert "quota" in step_names
        assert "network" in step_names
        assert "rbac" in step_names
        assert "harbor-project" in step_names
        assert "appset" in step_names

        # Done event
        assert len(done_events) == 1
        assert done_events[0].success is True

    @pytest.mark.asyncio
    async def test_provision_events_have_running_and_done(self, client, k8s_mock):
        lifecycle_bus._channels.pop("tenant:step-test", None)

        with (
            _patch_externals()[0],
            _patch_externals()[1],
            _patch_externals()[2],
            _patch_externals()[3],
            _patch_externals()[4],
            _patch_externals()[5],
            _patch_externals()[6],
        ):
            await client.post(
                "/api/v1/tenants",
                json={
                    "slug": "step-test",
                    "name": "Step Test",
                    "tier": "free",
                    "cpu_limit": "4",
                    "memory_limit": "8Gi",
                    "storage_limit": "50Gi",
                },
            )

        ch = lifecycle_bus.get("tenant:step-test")
        step_events = [e for e in ch.events if isinstance(e, LifecycleEvent)]

        # Each step should have a "running" followed by "done"
        running_steps = [e.step for e in step_events if e.status == "running"]
        done_steps = [e.step for e in step_events if e.status == "done"]
        assert set(running_steps) == set(done_steps)

    @pytest.mark.asyncio
    async def test_provision_events_streamable(self, client, k8s_mock):
        lifecycle_bus._channels.pop("tenant:stream-test", None)

        with (
            _patch_externals()[0],
            _patch_externals()[1],
            _patch_externals()[2],
            _patch_externals()[3],
            _patch_externals()[4],
            _patch_externals()[5],
            _patch_externals()[6],
        ):
            await client.post(
                "/api/v1/tenants",
                json={
                    "slug": "stream-test",
                    "name": "Stream Test",
                    "tier": "free",
                    "cpu_limit": "4",
                    "memory_limit": "8Gi",
                    "storage_limit": "50Gi",
                },
            )

        async with client.stream("GET", "/api/v1/tenants/stream-test/events") as r:
            assert r.status_code == 200
            body = ""
            async for chunk in r.aiter_text():
                body += chunk
                if "event: done" in body:
                    break
        assert "namespace" in body
        assert "appset" in body


# ===========================================================================
# TEST: Integration — service provision emits lifecycle events
# ===========================================================================


class TestServiceProvisionEvents:
    @pytest.mark.asyncio
    async def test_redis_provision_emits_events(self, client, k8s_mock):
        lifecycle_bus._channels.pop("service:svc-evt:app-redis", None)

        with (
            _patch_externals()[0],
            _patch_externals()[1],
            _patch_externals()[2],
            _patch_externals()[3],
            _patch_externals()[4],
            _patch_externals()[5],
            _patch_externals()[6],
            patch("app.services.managed_service.everest_client") as mock_ev,
        ):
            mock_ev.is_configured.return_value = False
            await client.post(
                "/api/v1/tenants",
                json={
                    "slug": "svc-evt",
                    "name": "Svc Event Test",
                    "tier": "free",
                    "cpu_limit": "4",
                    "memory_limit": "8Gi",
                    "storage_limit": "50Gi",
                },
            )
            r = await client.post(
                "/api/v1/tenants/svc-evt/services",
                json={
                    "name": "app-redis",
                    "service_type": "redis",
                    "tier": "dev",
                },
            )
        assert r.status_code == 201

        ch = lifecycle_bus.get("service:svc-evt:app-redis")
        assert ch is not None
        step_events = [e for e in ch.events if isinstance(e, LifecycleEvent)]
        assert any(e.step == "provision" and e.status == "done" for e in step_events)

    @pytest.mark.asyncio
    async def test_everest_provision_emits_events(self, client, k8s_mock):
        lifecycle_bus._channels.pop("service:ev-test:app-pg", None)

        with (
            _patch_externals()[0],
            _patch_externals()[1],
            _patch_externals()[2],
            _patch_externals()[3],
            _patch_externals()[4],
            _patch_externals()[5],
            _patch_externals()[6],
            patch("app.services.managed_service.everest_client") as mock_ev,
        ):
            mock_ev.is_configured.return_value = True
            mock_ev.create_database = AsyncMock()
            await client.post(
                "/api/v1/tenants",
                json={
                    "slug": "ev-test",
                    "name": "Everest Event Test",
                    "tier": "free",
                    "cpu_limit": "4",
                    "memory_limit": "8Gi",
                    "storage_limit": "50Gi",
                },
            )
            r = await client.post(
                "/api/v1/tenants/ev-test/services",
                json={
                    "name": "app-pg",
                    "service_type": "postgres",
                    "tier": "dev",
                },
            )
        assert r.status_code == 201

        ch = lifecycle_bus.get("service:ev-test:app-pg")
        assert ch is not None
        step_events = [e for e in ch.events if isinstance(e, LifecycleEvent)]
        provision_done = [e for e in step_events if e.step == "provision" and e.status == "done"]
        assert len(provision_done) == 1
        assert provision_done[0].detail is not None
        assert "secret" in provision_done[0].detail

    @pytest.mark.asyncio
    async def test_service_events_streamable(self, client, k8s_mock):
        lifecycle_bus._channels.pop("service:str-test:my-redis", None)

        with (
            _patch_externals()[0],
            _patch_externals()[1],
            _patch_externals()[2],
            _patch_externals()[3],
            _patch_externals()[4],
            _patch_externals()[5],
            _patch_externals()[6],
            patch("app.services.managed_service.everest_client") as mock_ev,
        ):
            mock_ev.is_configured.return_value = False
            await client.post(
                "/api/v1/tenants",
                json={
                    "slug": "str-test",
                    "name": "Stream Svc Test",
                    "tier": "free",
                    "cpu_limit": "4",
                    "memory_limit": "8Gi",
                    "storage_limit": "50Gi",
                },
            )
            await client.post(
                "/api/v1/tenants/str-test/services",
                json={
                    "name": "my-redis",
                    "service_type": "redis",
                    "tier": "dev",
                },
            )

        # Service provision channel has events but NOT marked done (waiting for ready)
        # So we read the channel directly instead of streaming
        ch = lifecycle_bus.get("service:str-test:my-redis")
        assert ch is not None
        step_events = [e for e in ch.events if hasattr(e, "step")]
        assert any(e.step == "provision" for e in step_events)


# ===========================================================================
# TEST: Integration — tenant deprovision emits lifecycle events
# ===========================================================================


class TestTenantDeprovisionEvents:
    @pytest.mark.asyncio
    async def test_deprovision_emits_delete_steps(self, client, k8s_mock):
        with (
            _patch_externals()[0],
            _patch_externals()[1],
            _patch_externals()[2],
            _patch_externals()[3],
            _patch_externals()[4],
            _patch_externals()[5],
            _patch_externals()[6],
            patch("app.services.managed_service.everest_client") as mock_ev,
        ):
            mock_ev.is_configured.return_value = False
            await client.post(
                "/api/v1/tenants",
                json={
                    "slug": "del-evt",
                    "name": "Del Event Test",
                    "tier": "free",
                    "cpu_limit": "4",
                    "memory_limit": "8Gi",
                    "storage_limit": "50Gi",
                },
            )

            # Clear provision events to focus on deprovision
            lifecycle_bus._channels.pop("tenant:del-evt", None)

            r = await client.delete("/api/v1/tenants/del-evt")
        assert r.status_code == 204

        ch = lifecycle_bus.get("tenant:del-evt")
        assert ch is not None
        assert ch.is_done

        step_events = [e for e in ch.events if isinstance(e, LifecycleEvent)]
        step_names = {e.step for e in step_events}
        assert "appset-delete" in step_names
        assert "namespace-delete" in step_names
        assert "harbor-delete" in step_names
