"""Redis-backed build queue with concurrency control.

Limits concurrent builds (globally and per-tenant) and queues additional
builds in FIFO order.  Mirrors the git_queue_service pattern.

Queue layout:
  haven:build:queue          — FIFO list (LPUSH enqueue, BRPOP dequeue)
  haven:build:active         — Set of active build job IDs
  haven:build:tenant:{slug}  — Set of active build IDs for a specific tenant
  haven:build:job:{id}       — Hash with job metadata / status
  haven:build:dlq            — Dead letter list for permanently failed builds
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Redis key constants
QUEUE_KEY = "haven:build:queue"
ACTIVE_KEY = "haven:build:active"
TENANT_ACTIVE_PREFIX = "haven:build:tenant:"
JOB_KEY_PREFIX = "haven:build:job:"
DLQ_KEY = "haven:build:dlq"
JOB_TTL_SECONDS = 86400  # 24 hours

# Default concurrency limits
DEFAULT_MAX_CONCURRENT = 3
DEFAULT_MAX_PER_TENANT = 1


class BuildJobStatus(StrEnum):
    """Possible states of a queued build job."""

    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class BuildQueueService:
    """Manages a Redis-backed build queue with concurrency control.

    Usage:
        service = BuildQueueService(redis_client)
        job_id, position = await service.enqueue_build("tenant-a", "my-app", deployment_id="dep-1")
        job = await service.dequeue_build()
        await service.complete_build(job["id"])
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        max_per_tenant: int = DEFAULT_MAX_PER_TENANT,
    ) -> None:
        self._redis = redis
        self.max_concurrent = max_concurrent
        self.max_per_tenant = max_per_tenant

    async def enqueue_build(
        self,
        tenant_slug: str,
        app_slug: str,
        *,
        deployment_id: str | None = None,
        repo_url: str = "",
        branch: str = "main",
        extra: dict[str, Any] | None = None,
    ) -> tuple[str, int]:
        """Enqueue a build job.

        Returns:
            (job_id, queue_position) — position is 0-based; 0 means it will be
            dequeued next (but may still be waiting for a concurrency slot).
        """
        job_id = str(uuid.uuid4())

        job: dict[str, Any] = {
            "id": job_id,
            "tenant_slug": tenant_slug,
            "app_slug": app_slug,
            "deployment_id": deployment_id or "",
            "repo_url": repo_url,
            "branch": branch,
            "status": BuildJobStatus.QUEUED.value,
            "enqueued_at": str(time.time()),
            **(extra or {}),
        }

        # Store job hash
        await self._redis.hset(
            f"{JOB_KEY_PREFIX}{job_id}",
            mapping={
                "id": job_id,
                "tenant_slug": tenant_slug,
                "app_slug": app_slug,
                "deployment_id": deployment_id or "",
                "repo_url": repo_url,
                "branch": branch,
                "status": BuildJobStatus.QUEUED.value,
                "enqueued_at": job["enqueued_at"],
                "error": "",
            },
        )
        await self._redis.expire(f"{JOB_KEY_PREFIX}{job_id}", JOB_TTL_SECONDS)

        # Push to FIFO queue
        await self._redis.lpush(QUEUE_KEY, json.dumps(job))

        position = await self.get_queue_position(job_id)
        logger.info(
            "Enqueued build job %s tenant=%s app=%s position=%d",
            job_id, tenant_slug, app_slug, position,
        )
        return job_id, position

    async def dequeue_build(self) -> dict[str, Any] | None:
        """Attempt to dequeue the next build job, respecting concurrency limits.

        Returns:
            The job dict if a job was successfully activated, or None if:
            - The queue is empty
            - Global concurrency limit reached
            - Per-tenant limit reached for the next job's tenant

        The caller should call complete_build(job_id) when done.
        """
        # Check global concurrency
        active_count = await self._redis.scard(ACTIVE_KEY)
        if active_count >= self.max_concurrent:
            return None

        # Peek at the queue (non-destructive) to check tenant limit
        # We scan from the tail (FIFO: LPUSH + RPOP)
        queue_len = await self._redis.llen(QUEUE_KEY)
        if queue_len == 0:
            return None

        # Try each item from the tail (oldest first) to find one that fits
        for i in range(queue_len):
            raw = await self._redis.lindex(QUEUE_KEY, -(i + 1))
            if raw is None:
                continue

            raw_str = raw.decode() if isinstance(raw, bytes) else raw
            job = json.loads(raw_str)
            tenant_slug = job.get("tenant_slug", "")

            # Check per-tenant limit
            tenant_key = f"{TENANT_ACTIVE_PREFIX}{tenant_slug}"
            tenant_active = await self._redis.scard(tenant_key)
            if tenant_active >= self.max_per_tenant:
                continue  # Skip this job, try the next one

            # Remove this specific item from the queue
            # Use LREM to remove exactly one occurrence of this value
            removed = await self._redis.lrem(QUEUE_KEY, 1, raw if isinstance(raw, bytes) else raw_str)
            if removed == 0:
                continue  # Already consumed by another worker

            # Activate the job
            job_id = job["id"]
            await self._redis.sadd(ACTIVE_KEY, job_id)
            await self._redis.sadd(tenant_key, job_id)

            # Update job status
            await self._redis.hset(
                f"{JOB_KEY_PREFIX}{job_id}",
                mapping={"status": BuildJobStatus.ACTIVE.value},
            )

            logger.info("Dequeued build job %s tenant=%s app=%s", job_id, tenant_slug, job.get("app_slug"))
            return job

        return None

    async def complete_build(self, job_id: str, *, failed: bool = False, error: str = "") -> None:
        """Mark a build job as completed or failed and remove from active sets.

        Args:
            job_id: The build job ID.
            failed: If True, mark as FAILED and optionally push to DLQ.
            error: Error message if failed.
        """
        # Get tenant_slug from job hash
        job_data = await self._redis.hgetall(f"{JOB_KEY_PREFIX}{job_id}")
        tenant_slug = ""
        if job_data:
            tenant_slug_raw = job_data.get(b"tenant_slug", job_data.get("tenant_slug", b""))
            tenant_slug = tenant_slug_raw.decode() if isinstance(tenant_slug_raw, bytes) else tenant_slug_raw

        # Remove from active sets
        await self._redis.srem(ACTIVE_KEY, job_id)
        if tenant_slug:
            await self._redis.srem(f"{TENANT_ACTIVE_PREFIX}{tenant_slug}", job_id)

        # Update status
        new_status = BuildJobStatus.FAILED if failed else BuildJobStatus.COMPLETED
        updates: dict[str, str] = {"status": new_status.value}
        if error:
            updates["error"] = error

        await self._redis.hset(f"{JOB_KEY_PREFIX}{job_id}", mapping=updates)
        await self._redis.expire(f"{JOB_KEY_PREFIX}{job_id}", JOB_TTL_SECONDS)

        if failed:
            await self._redis.lpush(DLQ_KEY, job_id)

        logger.info("Build job %s completed status=%s", job_id, new_status.value)

    async def get_queue_position(self, job_id: str) -> int:
        """Return the 0-based queue position for a job.

        Returns:
            Position (0 = next to be dequeued), or -1 if the job is active
            (already dequeued) or not found in the queue.
        """
        # Check if active
        is_active = await self._redis.sismember(ACTIVE_KEY, job_id)
        if is_active:
            return -1

        # Scan queue from tail (oldest = position 0)
        queue_len = await self._redis.llen(QUEUE_KEY)
        for i in range(queue_len):
            raw = await self._redis.lindex(QUEUE_KEY, -(i + 1))
            if raw is None:
                continue
            raw_str = raw.decode() if isinstance(raw, bytes) else raw
            try:
                job = json.loads(raw_str)
                if job.get("id") == job_id:
                    return i
            except (json.JSONDecodeError, TypeError):
                continue

        return -1

    async def get_queue_status(self) -> dict[str, Any]:
        """Return aggregate queue statistics.

        Returns:
            {
                "pending": int,
                "active": int,
                "active_jobs": list[str],
                "dlq": int,
                "max_concurrent": int,
                "max_per_tenant": int,
            }
        """
        pending = await self._redis.llen(QUEUE_KEY)
        active_members = await self._redis.smembers(ACTIVE_KEY)
        active_jobs = [
            m.decode() if isinstance(m, bytes) else m
            for m in active_members
        ]
        dlq = await self._redis.llen(DLQ_KEY)

        return {
            "pending": pending,
            "active": len(active_jobs),
            "active_jobs": active_jobs,
            "dlq": dlq,
            "max_concurrent": self.max_concurrent,
            "max_per_tenant": self.max_per_tenant,
        }

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Return metadata for a build job, or None if not found / expired."""
        data = await self._redis.hgetall(f"{JOB_KEY_PREFIX}{job_id}")
        if not data:
            return None
        return {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in data.items()
        }
