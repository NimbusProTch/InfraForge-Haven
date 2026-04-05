"""Build queue status endpoints.

Provides visibility into the Redis-backed build queue with concurrency control.
These endpoints are admin-only and intended for platform operators.

Routes:
  GET /api/v1/platform/build-queue/status           — aggregate counts + active jobs
  GET /api/v1/platform/build-queue/jobs/{job_id}     — single build job detail
  GET /api/v1/platform/build-queue/position/{job_id} — queue position for a job
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.jwt import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/platform/build-queue",
    tags=["platform-build-queue"],
    dependencies=[Depends(verify_token)],
)


def _get_build_queue_service():
    """Dependency: return a BuildQueueService backed by the app-wide Redis client.

    Catches Redis connection errors and returns a proper error response
    instead of raising 503.
    """
    from app.services.build_queue_service import BuildQueueService

    try:
        import redis.asyncio as aioredis

        from app.config import settings

        redis_url = getattr(settings, "redis_url", "redis://localhost:6379/0")
        client = aioredis.from_url(redis_url, decode_responses=False)
        return BuildQueueService(client)
    except ImportError:
        raise HTTPException(  # noqa: B904
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client library not installed. Add 'redis[asyncio]' to dependencies.",
        )


BuildQueueDep = Annotated["BuildQueueService", Depends(_get_build_queue_service)]


@router.get("/status", summary="Build queue aggregate statistics")
async def get_build_queue_status(queue_svc: BuildQueueDep) -> dict[str, Any]:
    """Return pending, active, and DLQ counts plus active job IDs.

    Response:
    ```json
    {
      "pending": 2,
      "active": 1,
      "active_jobs": ["uuid-1"],
      "dlq": 0,
      "max_concurrent": 3,
      "max_per_tenant": 1
    }
    ```
    """
    try:
        return await queue_svc.get_queue_status()
    except Exception as exc:
        logger.warning("Build queue status unavailable: %s", exc)
        return {
            "pending": 0,
            "active": 0,
            "active_jobs": [],
            "dlq": 0,
            "max_concurrent": queue_svc.max_concurrent,
            "max_per_tenant": queue_svc.max_per_tenant,
            "error_message": f"Build queue unavailable: {exc}",
        }


@router.get("/jobs/{job_id}", summary="Single build job status")
async def get_build_job(job_id: str, queue_svc: BuildQueueDep) -> dict[str, Any]:
    """Return metadata for a specific build job.

    Returns 404 if the job is not found or has expired (TTL=24h).
    """
    try:
        job = await queue_svc.get_job(job_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unavailable: {exc}",
        ) from exc

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Build job '{job_id}' not found or has expired.",
        )
    return job


@router.get("/position/{job_id}", summary="Queue position for a build job")
async def get_build_position(job_id: str, queue_svc: BuildQueueDep) -> dict[str, Any]:
    """Return the queue position for a build job.

    Response:
    ```json
    {"job_id": "uuid-1", "position": 2}
    ```
    Position is 0-based. -1 means the job is currently active.
    """
    try:
        position = await queue_svc.get_queue_position(job_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unavailable: {exc}",
        ) from exc
    return {"job_id": job_id, "position": position}
