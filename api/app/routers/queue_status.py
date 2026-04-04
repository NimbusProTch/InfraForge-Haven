"""Queue status endpoints for the Haven git writer queue.

Provides visibility into the Redis-backed git operation queue.
These endpoints are admin-only and intended for platform operators.

Routes:
  GET /api/v1/platform/queue/status        — aggregate counts
  GET /api/v1/platform/queue/jobs/{job_id} — single job detail
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.jwt import verify_token
from app.services.git_queue_service import GitQueueService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/platform/queue",
    tags=["platform-queue"],
    dependencies=[Depends(verify_token)],
)


def _get_queue_service() -> GitQueueService:
    """Dependency: return a GitQueueService backed by the app-wide Redis client.

    Falls back gracefully if Redis is not configured so that other API routes
    remain available even in environments without Redis.
    """
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        redis_url = getattr(settings, "redis_url", "redis://localhost:6379/0")
        client = aioredis.from_url(redis_url, decode_responses=False)
        return GitQueueService(client)
    except ImportError:
        raise HTTPException(  # noqa: B904
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client library not installed. Add 'redis[asyncio]' to dependencies.",
        )


QueueDep = Annotated[GitQueueService, Depends(_get_queue_service)]


@router.get("/status", summary="Queue aggregate statistics")
async def get_queue_status(queue_svc: QueueDep) -> dict[str, Any]:
    """Return pending and dead-letter counts.

    Response:
    ```json
    {
      "pending": 3,
      "dead_letter": 0
    }
    ```
    """
    pending = await queue_svc.queue_length()
    dead = await queue_svc.dead_letter_length()

    # Check if git-worker is alive by looking for heartbeat key or worker pod
    worker_alive = False
    try:
        # Worker sets a heartbeat key with TTL
        heartbeat = await queue_svc._redis.get("haven:git:worker:alive")
        worker_alive = heartbeat is not None
        if not worker_alive:
            # Fallback: check if any processing job exists (worker is busy)
            processing = await queue_svc._redis.get("haven:git:processing")
            worker_alive = processing is not None
            if not worker_alive:
                # Fallback 2: if queue is empty and DLQ is empty, assume worker is OK
                worker_alive = pending == 0 and dead == 0
    except Exception:
        pass

    return {
        "pending": pending,
        "processing": 0,
        "dead_letter": dead,
        "worker_alive": worker_alive,
    }


@router.get("/jobs/{job_id}", summary="Single job status")
async def get_job_status(job_id: str, queue_svc: QueueDep) -> dict[str, Any]:
    """Return status metadata for a specific job.

    Response fields: id, operation, repo, path, commit_message, status, retries, error.
    Returns 404 if the job is not found or has expired (TTL=24h).
    """
    job = await queue_svc.get_job_status(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found or has expired.",
        )
    return job
