"""Tests for the Redis-backed build queue with concurrency control.

Covers:
  - BuildQueueService: enqueue, dequeue, concurrency limits, per-tenant limits,
    queue position, complete/cleanup, queue status, DLQ
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.build_queue_service import (
    ACTIVE_KEY,
    DLQ_KEY,
    JOB_KEY_PREFIX,
    QUEUE_KEY,
    TENANT_ACTIVE_PREFIX,
    BuildJobStatus,
    BuildQueueService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock() -> MagicMock:
    """Return a fully mocked async Redis client with sensible defaults."""
    r = MagicMock()
    r.lpush = AsyncMock(return_value=1)
    r.llen = AsyncMock(return_value=0)
    r.lindex = AsyncMock(return_value=None)
    r.lrem = AsyncMock(return_value=1)
    r.hset = AsyncMock(return_value=1)
    r.hgetall = AsyncMock(return_value={})
    r.expire = AsyncMock(return_value=1)
    r.sadd = AsyncMock(return_value=1)
    r.srem = AsyncMock(return_value=1)
    r.scard = AsyncMock(return_value=0)
    r.sismember = AsyncMock(return_value=False)
    r.smembers = AsyncMock(return_value=set())
    r.brpop = AsyncMock(return_value=None)
    return r


def _make_queued_job(
    job_id: str = "test-job-1",
    tenant_slug: str = "tenant-a",
    app_slug: str = "my-app",
) -> dict[str, Any]:
    """Return a job dict as it would appear in the queue."""
    return {
        "id": job_id,
        "tenant_slug": tenant_slug,
        "app_slug": app_slug,
        "deployment_id": "dep-1",
        "repo_url": "https://github.com/test/repo",
        "branch": "main",
        "status": BuildJobStatus.QUEUED.value,
        "enqueued_at": "1234567890.0",
    }


# ---------------------------------------------------------------------------
# Enqueue tests
# ---------------------------------------------------------------------------


class TestEnqueueBuild:
    """Tests for enqueue_build()."""

    @pytest.mark.asyncio
    async def test_enqueue_returns_job_id_and_position(self) -> None:
        redis = _make_redis_mock()
        # After enqueue, llen returns 1, and lindex returns the job
        redis.llen.return_value = 1
        svc = BuildQueueService(redis)

        # Make lindex return the enqueued job (we need to capture the job_id)
        original_lpush = redis.lpush

        async def capture_lpush(key: str, data: str) -> int:
            job = json.loads(data)
            raw = data.encode()
            redis.lindex.return_value = raw
            # Make the job findable by scanning
            return 1

        redis.lpush = AsyncMock(side_effect=capture_lpush)

        job_id, position = await svc.enqueue_build(
            "tenant-a", "my-app", deployment_id="dep-1", repo_url="https://github.com/test/repo",
        )

        assert job_id  # UUID string
        assert isinstance(position, int)
        assert position >= 0

    @pytest.mark.asyncio
    async def test_enqueue_stores_job_hash(self) -> None:
        redis = _make_redis_mock()
        redis.llen.return_value = 0
        svc = BuildQueueService(redis)

        job_id, _ = await svc.enqueue_build("tenant-a", "my-app")

        # hset should be called with the job key
        hset_calls = redis.hset.call_args_list
        assert len(hset_calls) >= 1
        first_call_key = hset_calls[0][0][0]
        assert first_call_key == f"{JOB_KEY_PREFIX}{job_id}"

    @pytest.mark.asyncio
    async def test_enqueue_pushes_to_queue(self) -> None:
        redis = _make_redis_mock()
        redis.llen.return_value = 0
        svc = BuildQueueService(redis)

        await svc.enqueue_build("tenant-a", "my-app")

        redis.lpush.assert_called_once()
        call_args = redis.lpush.call_args[0]
        assert call_args[0] == QUEUE_KEY
        job_data = json.loads(call_args[1])
        assert job_data["tenant_slug"] == "tenant-a"
        assert job_data["app_slug"] == "my-app"

    @pytest.mark.asyncio
    async def test_enqueue_sets_ttl(self) -> None:
        redis = _make_redis_mock()
        redis.llen.return_value = 0
        svc = BuildQueueService(redis)

        job_id, _ = await svc.enqueue_build("tenant-a", "my-app")

        redis.expire.assert_called_once_with(f"{JOB_KEY_PREFIX}{job_id}", 86400)

    @pytest.mark.asyncio
    async def test_enqueue_with_extra_fields(self) -> None:
        redis = _make_redis_mock()
        redis.llen.return_value = 0
        svc = BuildQueueService(redis)

        job_id, _ = await svc.enqueue_build(
            "tenant-a", "my-app",
            extra={"dockerfile_path": "backend/Dockerfile"},
        )

        call_args = redis.lpush.call_args[0]
        job_data = json.loads(call_args[1])
        assert job_data["dockerfile_path"] == "backend/Dockerfile"


# ---------------------------------------------------------------------------
# Dequeue tests
# ---------------------------------------------------------------------------


class TestDequeueBuild:
    """Tests for dequeue_build()."""

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue(self) -> None:
        redis = _make_redis_mock()
        redis.llen.return_value = 0
        redis.scard.return_value = 0
        svc = BuildQueueService(redis)

        result = await svc.dequeue_build()
        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_returns_job(self) -> None:
        redis = _make_redis_mock()
        job = _make_queued_job()
        raw = json.dumps(job).encode()

        redis.scard.return_value = 0  # no active builds
        redis.llen.return_value = 1
        redis.lindex.return_value = raw
        redis.lrem.return_value = 1

        svc = BuildQueueService(redis)
        result = await svc.dequeue_build()

        assert result is not None
        assert result["id"] == "test-job-1"
        assert result["tenant_slug"] == "tenant-a"
        redis.sadd.assert_any_call(ACTIVE_KEY, "test-job-1")
        redis.sadd.assert_any_call(f"{TENANT_ACTIVE_PREFIX}tenant-a", "test-job-1")

    @pytest.mark.asyncio
    async def test_dequeue_global_limit_reached(self) -> None:
        redis = _make_redis_mock()
        redis.scard.return_value = 3  # at max_concurrent (default 3)

        svc = BuildQueueService(redis)
        result = await svc.dequeue_build()
        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_tenant_limit_reached_skips(self) -> None:
        redis = _make_redis_mock()
        job = _make_queued_job()
        raw = json.dumps(job).encode()

        # Global: 0 active, Tenant: 1 active (at max_per_tenant=1)
        call_count = 0

        async def scard_side_effect(key: str) -> int:
            nonlocal call_count
            call_count += 1
            if key == ACTIVE_KEY:
                return 0
            if key == f"{TENANT_ACTIVE_PREFIX}tenant-a":
                return 1  # tenant-a at limit
            return 0

        redis.scard = AsyncMock(side_effect=scard_side_effect)
        redis.llen.return_value = 1
        redis.lindex.return_value = raw

        svc = BuildQueueService(redis)
        result = await svc.dequeue_build()
        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_skips_tenant_at_limit_picks_next(self) -> None:
        """When tenant-a is at limit but tenant-b has capacity, dequeue tenant-b's job."""
        redis = _make_redis_mock()
        job_a = _make_queued_job(job_id="job-a", tenant_slug="tenant-a")
        job_b = _make_queued_job(job_id="job-b", tenant_slug="tenant-b")
        raw_a = json.dumps(job_a).encode()
        raw_b = json.dumps(job_b).encode()

        async def scard_side_effect(key: str) -> int:
            if key == ACTIVE_KEY:
                return 0
            if key == f"{TENANT_ACTIVE_PREFIX}tenant-a":
                return 1  # tenant-a at limit
            return 0  # tenant-b has capacity

        redis.scard = AsyncMock(side_effect=scard_side_effect)
        redis.llen.return_value = 2

        # lindex returns items from tail: index -1 is oldest (job_a), index -2 is job_b
        async def lindex_side_effect(key: str, idx: int) -> bytes | None:
            if idx == -1:
                return raw_a  # oldest = tenant-a (blocked)
            if idx == -2:
                return raw_b  # next = tenant-b (ok)
            return None

        redis.lindex = AsyncMock(side_effect=lindex_side_effect)
        redis.lrem.return_value = 1

        svc = BuildQueueService(redis)
        result = await svc.dequeue_build()

        assert result is not None
        assert result["id"] == "job-b"
        assert result["tenant_slug"] == "tenant-b"

    @pytest.mark.asyncio
    async def test_dequeue_custom_concurrency_limits(self) -> None:
        redis = _make_redis_mock()
        redis.scard.return_value = 5  # 5 active builds

        svc = BuildQueueService(redis, max_concurrent=10, max_per_tenant=2)
        # 5 < 10 so global limit not reached; queue is empty though
        redis.llen.return_value = 0
        result = await svc.dequeue_build()
        assert result is None

        # Now at 10 -> blocked
        redis.scard.return_value = 10
        redis.llen.return_value = 1
        result = await svc.dequeue_build()
        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_updates_job_status(self) -> None:
        redis = _make_redis_mock()
        job = _make_queued_job()
        raw = json.dumps(job).encode()
        redis.scard.return_value = 0
        redis.llen.return_value = 1
        redis.lindex.return_value = raw
        redis.lrem.return_value = 1

        svc = BuildQueueService(redis)
        await svc.dequeue_build()

        # Check hset was called with ACTIVE status
        hset_calls = redis.hset.call_args_list
        status_update = [c for c in hset_calls if "status" in str(c)]
        assert len(status_update) > 0


# ---------------------------------------------------------------------------
# Complete build tests
# ---------------------------------------------------------------------------


class TestCompleteBuild:
    """Tests for complete_build()."""

    @pytest.mark.asyncio
    async def test_complete_success(self) -> None:
        redis = _make_redis_mock()
        redis.hgetall.return_value = {b"tenant_slug": b"tenant-a"}

        svc = BuildQueueService(redis)
        await svc.complete_build("job-1")

        redis.srem.assert_any_call(ACTIVE_KEY, "job-1")
        redis.srem.assert_any_call(f"{TENANT_ACTIVE_PREFIX}tenant-a", "job-1")
        hset_call = redis.hset.call_args
        assert hset_call[1]["mapping"]["status"] == BuildJobStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_complete_failed_pushes_to_dlq(self) -> None:
        redis = _make_redis_mock()
        redis.hgetall.return_value = {b"tenant_slug": b"tenant-a"}

        svc = BuildQueueService(redis)
        await svc.complete_build("job-1", failed=True, error="OOM killed")

        redis.srem.assert_any_call(ACTIVE_KEY, "job-1")
        hset_call = redis.hset.call_args
        assert hset_call[1]["mapping"]["status"] == BuildJobStatus.FAILED.value
        assert hset_call[1]["mapping"]["error"] == "OOM killed"
        redis.lpush.assert_called_once_with(DLQ_KEY, "job-1")

    @pytest.mark.asyncio
    async def test_complete_refreshes_ttl(self) -> None:
        redis = _make_redis_mock()
        redis.hgetall.return_value = {b"tenant_slug": b"tenant-a"}

        svc = BuildQueueService(redis)
        await svc.complete_build("job-1")

        redis.expire.assert_called_once_with(f"{JOB_KEY_PREFIX}job-1", 86400)

    @pytest.mark.asyncio
    async def test_complete_missing_tenant(self) -> None:
        """complete_build should not fail if job hash is empty/expired."""
        redis = _make_redis_mock()
        redis.hgetall.return_value = {}

        svc = BuildQueueService(redis)
        # Should not raise
        await svc.complete_build("expired-job")
        redis.srem.assert_any_call(ACTIVE_KEY, "expired-job")


# ---------------------------------------------------------------------------
# Queue position tests
# ---------------------------------------------------------------------------


class TestQueuePosition:
    """Tests for get_queue_position()."""

    @pytest.mark.asyncio
    async def test_position_active_returns_minus_one(self) -> None:
        redis = _make_redis_mock()
        redis.sismember.return_value = True  # job is active

        svc = BuildQueueService(redis)
        pos = await svc.get_queue_position("active-job")
        assert pos == -1

    @pytest.mark.asyncio
    async def test_position_not_found_returns_minus_one(self) -> None:
        redis = _make_redis_mock()
        redis.sismember.return_value = False
        redis.llen.return_value = 0

        svc = BuildQueueService(redis)
        pos = await svc.get_queue_position("ghost-job")
        assert pos == -1

    @pytest.mark.asyncio
    async def test_position_found_in_queue(self) -> None:
        redis = _make_redis_mock()
        redis.sismember.return_value = False

        job1 = _make_queued_job(job_id="first")
        job2 = _make_queued_job(job_id="second")
        redis.llen.return_value = 2

        async def lindex_side(key: str, idx: int) -> bytes | None:
            if idx == -1:
                return json.dumps(job1).encode()  # oldest (position 0)
            if idx == -2:
                return json.dumps(job2).encode()  # position 1
            return None

        redis.lindex = AsyncMock(side_effect=lindex_side)

        svc = BuildQueueService(redis)

        pos = await svc.get_queue_position("first")
        assert pos == 0

        pos = await svc.get_queue_position("second")
        assert pos == 1

    @pytest.mark.asyncio
    async def test_position_handles_corrupt_data(self) -> None:
        redis = _make_redis_mock()
        redis.sismember.return_value = False
        redis.llen.return_value = 1
        redis.lindex.return_value = b"not-valid-json"

        svc = BuildQueueService(redis)
        pos = await svc.get_queue_position("any-job")
        assert pos == -1


# ---------------------------------------------------------------------------
# Queue status tests
# ---------------------------------------------------------------------------


class TestQueueStatus:
    """Tests for get_queue_status()."""

    @pytest.mark.asyncio
    async def test_queue_status_empty(self) -> None:
        redis = _make_redis_mock()
        redis.llen.return_value = 0
        redis.smembers.return_value = set()

        svc = BuildQueueService(redis, max_concurrent=3, max_per_tenant=1)
        status = await svc.get_queue_status()

        assert status["pending"] == 0
        assert status["active"] == 0
        assert status["active_jobs"] == []
        assert status["dlq"] == 0
        assert status["max_concurrent"] == 3
        assert status["max_per_tenant"] == 1

    @pytest.mark.asyncio
    async def test_queue_status_with_active(self) -> None:
        redis = _make_redis_mock()

        # Pending queue has 2 items
        call_count = 0

        async def llen_side(key: str) -> int:
            nonlocal call_count
            call_count += 1
            if key == QUEUE_KEY:
                return 2
            return 0  # DLQ

        redis.llen = AsyncMock(side_effect=llen_side)
        redis.smembers.return_value = {b"job-1", b"job-2"}

        svc = BuildQueueService(redis)
        status = await svc.get_queue_status()

        assert status["pending"] == 2
        assert status["active"] == 2
        assert set(status["active_jobs"]) == {"job-1", "job-2"}


# ---------------------------------------------------------------------------
# Get job tests
# ---------------------------------------------------------------------------


class TestGetJob:
    """Tests for get_job()."""

    @pytest.mark.asyncio
    async def test_get_existing_job(self) -> None:
        redis = _make_redis_mock()
        redis.hgetall.return_value = {
            b"id": b"job-1",
            b"tenant_slug": b"tenant-a",
            b"status": b"queued",
        }

        svc = BuildQueueService(redis)
        job = await svc.get_job("job-1")

        assert job is not None
        assert job["id"] == "job-1"
        assert job["tenant_slug"] == "tenant-a"
        assert job["status"] == "queued"

    @pytest.mark.asyncio
    async def test_get_missing_job(self) -> None:
        redis = _make_redis_mock()
        redis.hgetall.return_value = {}

        svc = BuildQueueService(redis)
        job = await svc.get_job("nonexistent")
        assert job is None


# ---------------------------------------------------------------------------
# BuildJobStatus enum tests
# ---------------------------------------------------------------------------


class TestBuildJobStatus:
    """Tests for BuildJobStatus enum values."""

    def test_status_values(self) -> None:
        assert BuildJobStatus.QUEUED.value == "queued"
        assert BuildJobStatus.ACTIVE.value == "active"
        assert BuildJobStatus.COMPLETED.value == "completed"
        assert BuildJobStatus.FAILED.value == "failed"

    def test_status_is_str(self) -> None:
        assert isinstance(BuildJobStatus.QUEUED, str)
        assert BuildJobStatus.ACTIVE == "active"
