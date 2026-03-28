"""Queue-based git writer service.

Enqueues git file operations (create/update/delete) to a Redis FIFO queue.
A single worker processes operations sequentially to prevent git conflicts.

Queue layout:
  haven:git:queue        — FIFO list (LPUSH enqueue, BRPOP dequeue)
  haven:git:job:{id}     — Hash with job status/metadata
  haven:git:dead         — Dead letter list for failed jobs (3 retries)
"""

from __future__ import annotations

import json
import logging
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Redis key constants
QUEUE_KEY = "haven:git:queue"
DEAD_LETTER_KEY = "haven:git:dead"
JOB_KEY_PREFIX = "haven:git:job:"
JOB_TTL_SECONDS = 86400  # 24 hours


class GitOperation(str, Enum):
    """Supported git file operations."""

    CREATE_FILE = "CREATE_FILE"
    UPDATE_FILE = "UPDATE_FILE"
    DELETE_FILE = "DELETE_FILE"


class JobStatus(str, Enum):
    """Possible states of a queued git job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class GitQueueService:
    """Enqueues git operations to Redis for sequential processing by git_worker.

    Usage:
        service = GitQueueService(redis_client)
        job_id = await service.enqueue(
            GitOperation.UPDATE_FILE,
            {
                "repo": "InfraForge-Haven",
                "path": "gitops/tenants/gemeente-a/my-app/values.yaml",
                "content": "image:\\n  tag: abc123\\n",
                "commit_message": "[haven] deploy gemeente-a/my-app",
                "author": "Haven Platform <haven@haven.dev>",
            }
        )
    """

    def __init__(self, redis: "aioredis.Redis") -> None:
        self._redis = redis

    async def enqueue(
        self,
        operation: GitOperation,
        payload: dict[str, Any],
    ) -> str:
        """Push a git operation to the queue.

        Args:
            operation: One of CREATE_FILE, UPDATE_FILE, DELETE_FILE.
            payload: Must contain: repo, path, commit_message, author.
                     CREATE_FILE / UPDATE_FILE also require: content.

        Returns:
            job_id (str UUID4) — use with get_job_status() to poll progress.

        Raises:
            ValueError: If required payload fields are missing.
        """
        required = {"repo", "path", "commit_message", "author"}
        if operation in (GitOperation.CREATE_FILE, GitOperation.UPDATE_FILE):
            required.add("content")

        missing = required - payload.keys()
        if missing:
            raise ValueError(f"Missing required payload fields: {missing}")

        job_id = str(uuid.uuid4())
        job: dict[str, Any] = {
            "id": job_id,
            "operation": operation.value,
            "payload": payload,
            "status": JobStatus.PENDING.value,
            "retries": 0,
            "error": None,
        }

        # Store job metadata
        await self._redis.hset(
            f"{JOB_KEY_PREFIX}{job_id}",
            mapping={
                "id": job_id,
                "operation": operation.value,
                "repo": payload.get("repo", ""),
                "path": payload.get("path", ""),
                "commit_message": payload.get("commit_message", ""),
                "status": JobStatus.PENDING.value,
                "retries": "0",
                "error": "",
            },
        )
        await self._redis.expire(f"{JOB_KEY_PREFIX}{job_id}", JOB_TTL_SECONDS)

        # Push to queue (LPUSH for FIFO when combined with BRPOP)
        await self._redis.lpush(QUEUE_KEY, json.dumps(job))

        logger.info("Enqueued git job %s op=%s path=%s", job_id, operation.value, payload.get("path"))
        return job_id

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Return status metadata for a job, or None if not found / expired."""
        data = await self._redis.hgetall(f"{JOB_KEY_PREFIX}{job_id}")
        if not data:
            return None
        # Redis returns bytes — decode if needed
        return {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in data.items()
        }

    async def queue_length(self) -> int:
        """Return number of pending jobs in the queue."""
        return await self._redis.llen(QUEUE_KEY)

    async def dead_letter_length(self) -> int:
        """Return number of jobs in the dead letter queue."""
        return await self._redis.llen(DEAD_LETTER_KEY)

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str = "",
        retries: int | None = None,
    ) -> None:
        """Update job status hash in Redis (called by worker)."""
        updates: dict[str, str] = {"status": status.value, "error": error}
        if retries is not None:
            updates["retries"] = str(retries)

        await self._redis.hset(f"{JOB_KEY_PREFIX}{job_id}", mapping=updates)
        # Refresh TTL on status updates
        await self._redis.expire(f"{JOB_KEY_PREFIX}{job_id}", JOB_TTL_SECONDS)
