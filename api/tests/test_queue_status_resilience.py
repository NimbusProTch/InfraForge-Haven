"""Tests for queue status endpoint resilience.

Covers:
  - Redis connection failure returns graceful response with error_message
  - Successful Redis connection returns proper counts
  - worker_alive detection logic (heartbeat, processing key, fallback)
  - Queue service None (Redis unavailable) returns safe defaults
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.jwt import verify_token
from app.deps import get_db, get_k8s
from app.main import app
from app.routers.queue_status import _get_queue_service

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ac_with_queue_override(db_session: AsyncSession, queue_svc):
    """Create an AsyncClient with the queue service dependency overridden."""

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_k8s] = lambda: MagicMock()
    app.dependency_overrides[verify_token] = lambda: {
        "sub": "admin-user",
        "email": "admin@haven.nl",
        "realm_access": {"roles": ["platform-admin"]},
    }
    app.dependency_overrides[_get_queue_service] = lambda: queue_svc

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestQueueStatusResilience:
    """Tests for GET /api/v1/platform/queue/status resilience."""

    @pytest.mark.asyncio
    async def test_redis_unavailable_returns_graceful_response(self, db_session: AsyncSession):
        """When Redis is unavailable (queue_svc is None), endpoint returns safe defaults."""
        async with _make_ac_with_queue_override(db_session, None) as ac:
            resp = await ac.get("/api/v1/platform/queue/status")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"] == 0
        assert data["dead_letter"] == 0
        assert data["worker_alive"] is False
        assert "error_message" in data

    @pytest.mark.asyncio
    async def test_redis_connection_failure_returns_error(self, db_session: AsyncSession):
        """When Redis connection fails during status check, endpoint returns error gracefully."""
        mock_svc = MagicMock()
        mock_svc.queue_length = AsyncMock(side_effect=ConnectionError("Connection refused"))
        mock_svc.dead_letter_length = AsyncMock(return_value=0)

        async with _make_ac_with_queue_override(db_session, mock_svc) as ac:
            resp = await ac.get("/api/v1/platform/queue/status")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"] == 0
        assert data["worker_alive"] is False
        assert "error_message" in data
        assert "connection" in data["error_message"].lower()

    @pytest.mark.asyncio
    async def test_successful_redis_returns_counts(self, db_session: AsyncSession):
        """When Redis is healthy, endpoint returns actual queue counts."""
        mock_svc = MagicMock()
        mock_svc.queue_length = AsyncMock(return_value=5)
        mock_svc.dead_letter_length = AsyncMock(return_value=2)
        mock_svc._redis = MagicMock()
        mock_svc._redis.get = AsyncMock(return_value=b"1")  # heartbeat present

        async with _make_ac_with_queue_override(db_session, mock_svc) as ac:
            resp = await ac.get("/api/v1/platform/queue/status")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"] == 5
        assert data["dead_letter"] == 2
        assert data["worker_alive"] is True

    @pytest.mark.asyncio
    async def test_worker_alive_via_heartbeat(self, db_session: AsyncSession):
        """Worker is alive when heartbeat key exists in Redis."""
        mock_svc = MagicMock()
        mock_svc.queue_length = AsyncMock(return_value=3)
        mock_svc.dead_letter_length = AsyncMock(return_value=0)
        mock_svc._redis = MagicMock()
        mock_svc._redis.get = AsyncMock(return_value=b"alive")

        async with _make_ac_with_queue_override(db_session, mock_svc) as ac:
            resp = await ac.get("/api/v1/platform/queue/status")

        app.dependency_overrides.clear()

        data = resp.json()
        assert data["worker_alive"] is True

    @pytest.mark.asyncio
    async def test_worker_alive_via_processing_key(self, db_session: AsyncSession):
        """Worker is alive when no heartbeat but processing key exists."""
        mock_svc = MagicMock()
        mock_svc.queue_length = AsyncMock(return_value=1)
        mock_svc.dead_letter_length = AsyncMock(return_value=0)
        mock_redis = MagicMock()
        # First get: heartbeat = None, second get: processing = b"job-123"
        mock_redis.get = AsyncMock(side_effect=[None, b"job-123"])
        mock_svc._redis = mock_redis

        async with _make_ac_with_queue_override(db_session, mock_svc) as ac:
            resp = await ac.get("/api/v1/platform/queue/status")

        app.dependency_overrides.clear()

        data = resp.json()
        assert data["worker_alive"] is True

    @pytest.mark.asyncio
    async def test_worker_alive_fallback_empty_queues(self, db_session: AsyncSession):
        """Worker assumed alive when no heartbeat, no processing, but queues empty."""
        mock_svc = MagicMock()
        mock_svc.queue_length = AsyncMock(return_value=0)
        mock_svc.dead_letter_length = AsyncMock(return_value=0)
        mock_redis = MagicMock()
        # heartbeat = None, processing = None
        mock_redis.get = AsyncMock(return_value=None)
        mock_svc._redis = mock_redis

        async with _make_ac_with_queue_override(db_session, mock_svc) as ac:
            resp = await ac.get("/api/v1/platform/queue/status")

        app.dependency_overrides.clear()

        data = resp.json()
        # Fallback: queues empty = worker assumed OK
        assert data["worker_alive"] is True

    @pytest.mark.asyncio
    async def test_worker_not_alive_when_pending_but_no_heartbeat(self, db_session: AsyncSession):
        """Worker NOT alive when pending > 0 but no heartbeat and no processing."""
        mock_svc = MagicMock()
        mock_svc.queue_length = AsyncMock(return_value=3)
        mock_svc.dead_letter_length = AsyncMock(return_value=1)
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_svc._redis = mock_redis

        async with _make_ac_with_queue_override(db_session, mock_svc) as ac:
            resp = await ac.get("/api/v1/platform/queue/status")

        app.dependency_overrides.clear()

        data = resp.json()
        # pending=3, dlq=1, no heartbeat, no processing -> worker not alive
        assert data["worker_alive"] is False

    @pytest.mark.asyncio
    async def test_response_always_has_required_fields(self, db_session: AsyncSession):
        """Response always includes pending, processing, dead_letter, worker_alive."""
        async with _make_ac_with_queue_override(db_session, None) as ac:
            resp = await ac.get("/api/v1/platform/queue/status")

        app.dependency_overrides.clear()

        data = resp.json()
        assert "pending" in data
        assert "processing" in data
        assert "dead_letter" in data
        assert "worker_alive" in data
