"""Tests for the queue-based git writer (Sprint I-3).

Covers:
  - GitQueueService: enqueue, validation, get_job_status, queue_length, dead_letter_length
  - GitWorker: successful processing, retry on failure, dead letter after MAX_RETRIES
  - Queue status router endpoints
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.git_queue_service import (
    DEAD_LETTER_KEY,
    JOB_KEY_PREFIX,
    QUEUE_KEY,
    GitOperation,
    GitQueueService,
    JobStatus,
)
from app.workers.git_worker import MAX_RETRIES, GitWorker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock() -> MagicMock:
    """Return a fully mocked async Redis client."""
    r = MagicMock()
    r.lpush = AsyncMock(return_value=1)
    r.brpop = AsyncMock(return_value=None)
    r.llen = AsyncMock(return_value=0)
    r.hset = AsyncMock(return_value=1)
    r.hgetall = AsyncMock(return_value={})
    r.expire = AsyncMock(return_value=1)
    return r


def _make_app_payload(
    *,
    operation: GitOperation = GitOperation.UPDATE_FILE,
    path: str = "gitops/tenants/gem-a/my-app/values.yaml",
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "repo": "InfraForge-Haven",
        "path": path,
        "commit_message": "[haven] test commit",
        "author": "Haven Platform <haven@haven.dev>",
        "tenant_slug": "gem-a",
        "app_slug": "my-app",
        "values": {"image": {"tag": "abc123"}},
    }
    if operation == GitOperation.DELETE_FILE:
        base.pop("values", None)
    else:
        base["content"] = "image:\n  tag: abc123\n"
    return base


# ---------------------------------------------------------------------------
# GitQueueService tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_returns_uuid_string():
    """enqueue() should return a valid UUID4 string."""
    redis = _make_redis_mock()
    svc = GitQueueService(redis)

    job_id = await svc.enqueue(GitOperation.UPDATE_FILE, _make_app_payload())

    assert isinstance(job_id, str)
    parsed = uuid.UUID(job_id, version=4)
    assert str(parsed) == job_id


@pytest.mark.asyncio
async def test_enqueue_calls_lpush_with_serialized_job():
    """enqueue() should LPUSH a JSON-serialised job dict to QUEUE_KEY."""
    redis = _make_redis_mock()
    svc = GitQueueService(redis)

    payload = _make_app_payload()
    job_id = await svc.enqueue(GitOperation.CREATE_FILE, payload)

    redis.lpush.assert_awaited_once()
    call_args = redis.lpush.call_args
    assert call_args[0][0] == QUEUE_KEY
    raw_job = json.loads(call_args[0][1])
    assert raw_job["id"] == job_id
    assert raw_job["operation"] == GitOperation.CREATE_FILE.value
    assert raw_job["status"] == JobStatus.PENDING.value


@pytest.mark.asyncio
async def test_enqueue_stores_job_hash_in_redis():
    """enqueue() must persist job metadata via hset."""
    redis = _make_redis_mock()
    svc = GitQueueService(redis)

    payload = _make_app_payload()
    job_id = await svc.enqueue(GitOperation.UPDATE_FILE, payload)

    redis.hset.assert_awaited()
    key_arg = redis.hset.call_args[0][0]
    assert key_arg == f"{JOB_KEY_PREFIX}{job_id}"


@pytest.mark.asyncio
async def test_enqueue_validates_missing_content_for_update():
    """UPDATE_FILE without 'content' must raise ValueError."""
    redis = _make_redis_mock()
    svc = GitQueueService(redis)

    bad_payload = {
        "repo": "InfraForge-Haven",
        "path": "gitops/tenants/gem-a/my-app/values.yaml",
        "commit_message": "[haven] oops",
        "author": "Haven Platform <haven@haven.dev>",
        # 'content' missing intentionally
    }
    with pytest.raises(ValueError, match="content"):
        await svc.enqueue(GitOperation.UPDATE_FILE, bad_payload)


@pytest.mark.asyncio
async def test_enqueue_delete_does_not_require_content():
    """DELETE_FILE should succeed without 'content' field."""
    redis = _make_redis_mock()
    svc = GitQueueService(redis)

    payload = {
        "repo": "InfraForge-Haven",
        "path": "gitops/tenants/gem-a/my-app/values.yaml",
        "commit_message": "[haven] delete gem-a/my-app",
        "author": "Haven Platform <haven@haven.dev>",
        "tenant_slug": "gem-a",
        "app_slug": "my-app",
    }
    job_id = await svc.enqueue(GitOperation.DELETE_FILE, payload)
    assert job_id  # did not raise


@pytest.mark.asyncio
async def test_get_job_status_returns_none_for_missing_job():
    """get_job_status() returns None when Redis hgetall yields empty dict."""
    redis = _make_redis_mock()
    redis.hgetall = AsyncMock(return_value={})
    svc = GitQueueService(redis)

    result = await svc.get_job_status("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_get_job_status_decodes_bytes():
    """get_job_status() decodes byte keys/values returned by Redis."""
    redis = _make_redis_mock()
    redis.hgetall = AsyncMock(
        return_value={
            b"id": b"abc123",
            b"status": b"completed",
            b"operation": b"UPDATE_FILE",
        }
    )
    svc = GitQueueService(redis)

    result = await svc.get_job_status("abc123")
    assert result == {"id": "abc123", "status": "completed", "operation": "UPDATE_FILE"}


@pytest.mark.asyncio
async def test_queue_length_and_dead_letter_length():
    """queue_length() and dead_letter_length() proxy llen correctly."""
    redis = _make_redis_mock()
    redis.llen = AsyncMock(side_effect=[5, 2])
    svc = GitQueueService(redis)

    assert await svc.queue_length() == 5
    assert await svc.dead_letter_length() == 2


# ---------------------------------------------------------------------------
# GitWorker tests
# ---------------------------------------------------------------------------


def _make_worker_job(operation: GitOperation = GitOperation.UPDATE_FILE) -> dict[str, Any]:
    payload = _make_app_payload(operation=operation)
    return {
        "id": str(uuid.uuid4()),
        "operation": operation.value,
        "payload": payload,
        "status": JobStatus.PENDING.value,
        "retries": 0,
        "error": None,
    }


@pytest.mark.asyncio
async def test_worker_processes_job_successfully():
    """Worker marks job COMPLETED after a successful gitops call."""
    redis = _make_redis_mock()
    gitops = MagicMock()
    gitops.write_app_values = AsyncMock(return_value="sha123")

    worker = GitWorker(redis, gitops)
    job = _make_worker_job(GitOperation.UPDATE_FILE)

    await worker._process_job(job)

    gitops.write_app_values.assert_awaited_once_with("gem-a", "my-app", {"image": {"tag": "abc123"}})
    # Final status update should be COMPLETED
    status_calls = [c for c in redis.hset.call_args_list if "completed" in str(c)]
    assert status_calls, "Expected a COMPLETED status update"


@pytest.mark.asyncio
async def test_worker_retries_on_failure():
    """Worker re-queues the job with incremented retries on transient failure."""
    redis = _make_redis_mock()
    gitops = MagicMock()
    gitops.write_app_values = AsyncMock(side_effect=RuntimeError("git push failed"))

    worker = GitWorker(redis, gitops)
    job = _make_worker_job(GitOperation.UPDATE_FILE)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await worker._process_job(job)

    # Job should be re-queued (lpush called for retry)
    redis.lpush.assert_awaited()
    re_queued_raw = redis.lpush.call_args[0][1]
    re_queued = json.loads(re_queued_raw)
    assert re_queued["retries"] == 1


@pytest.mark.asyncio
async def test_worker_moves_to_dead_letter_after_max_retries():
    """Job is pushed to DLQ and marked FAILED after MAX_RETRIES attempts."""
    redis = _make_redis_mock()
    gitops = MagicMock()
    gitops.write_app_values = AsyncMock(side_effect=RuntimeError("persistent failure"))

    worker = GitWorker(redis, gitops)
    job = _make_worker_job(GitOperation.UPDATE_FILE)
    job["retries"] = MAX_RETRIES - 1  # One more failure triggers dead letter

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await worker._process_job(job)

    # Should push to DLQ key
    dlq_calls = [c for c in redis.lpush.call_args_list if c[0][0] == DEAD_LETTER_KEY]
    assert dlq_calls, "Expected job to be pushed to dead letter queue"

    # Status should be FAILED
    failed_calls = [c for c in redis.hset.call_args_list if "failed" in str(c)]
    assert failed_calls, "Expected FAILED status update"


@pytest.mark.asyncio
async def test_worker_processes_delete_operation():
    """Worker routes DELETE_FILE to gitops.delete_app."""
    redis = _make_redis_mock()
    gitops = MagicMock()
    gitops.delete_app = AsyncMock(return_value="sha456")

    worker = GitWorker(redis, gitops)
    job = _make_worker_job(GitOperation.DELETE_FILE)

    await worker._process_job(job)

    gitops.delete_app.assert_awaited_once_with("gem-a", "my-app")
