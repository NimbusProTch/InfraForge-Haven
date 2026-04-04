"""Single-worker Redis queue processor for git operations.

Reads jobs from haven:git:queue (BRPOP, blocking pop from right end)
and executes them sequentially via GitOpsService.  Sequential processing
prevents concurrent git conflicts.

Retry policy:
  - Up to MAX_RETRIES=3 attempts per job
  - Exponential backoff: 2^attempt seconds (2s, 4s, 8s)
  - After MAX_RETRIES failures: job pushed to haven:git:dead

Run as standalone process:
    python -m app.workers.git_worker

Or import and call run() in an asyncio event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from typing import TYPE_CHECKING, Any

from app.services.git_queue_service import (
    DEAD_LETTER_KEY,
    QUEUE_KEY,
    GitOperation,
    GitQueueService,
    JobStatus,
)
from app.services.gitops_service import GitOpsService

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BRPOP_TIMEOUT = 5  # seconds to block on BRPOP before looping (allows clean shutdown)


class GitWorker:
    """Sequential git queue processor backed by Redis and GitOpsService.

    One instance per process — do not run multiple workers in the same process
    as that would defeat the purpose of serial git commits.
    """

    def __init__(self, redis: aioredis.Redis, gitops: GitOpsService) -> None:
        self._redis = redis
        self._gitops = gitops
        self._queue_svc = GitQueueService(redis)
        self._running = False

    async def run(self) -> None:
        """Start the worker loop. Blocks until stop() is called."""
        self._running = True
        logger.info("Git worker started, listening on %s", QUEUE_KEY)

        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, self.stop)
        loop.add_signal_handler(signal.SIGINT, self.stop)

        while self._running:
            try:
                # Set heartbeat (TTL 15s — expires if worker dies)
                await self._redis.set("haven:git:worker:alive", "1", ex=15)

                result = await self._redis.brpop(QUEUE_KEY, timeout=BRPOP_TIMEOUT)
                if result is None:
                    # Timeout — loop back to check _running flag
                    continue

                _, raw = result
                job: dict[str, Any] = json.loads(raw)
                await self._process_job(job)

            except Exception:
                logger.exception("Unexpected error in worker loop — continuing")
                await asyncio.sleep(1)

        logger.info("Git worker stopped")

    def stop(self) -> None:
        """Signal the worker to stop after the current job completes."""
        logger.info("Git worker shutting down...")
        self._running = False

    async def _process_job(self, job: dict[str, Any]) -> None:
        """Execute a single job with retry + dead-letter handling."""
        job_id: str = job["id"]
        operation = GitOperation(job["operation"])
        payload: dict[str, Any] = job["payload"]
        retries: int = job.get("retries", 0)

        await self._queue_svc.update_job_status(job_id, JobStatus.PROCESSING, retries=retries)
        logger.info(
            "Processing job %s op=%s path=%s (attempt %d)",
            job_id,
            operation.value,
            payload.get("path"),
            retries + 1,
        )

        try:
            await self._execute_operation(operation, payload)
            await self._queue_svc.update_job_status(job_id, JobStatus.COMPLETED, retries=retries)
            logger.info("Job %s completed", job_id)

        except Exception as exc:
            retries += 1
            error_msg = str(exc)
            logger.warning("Job %s failed (attempt %d/%d): %s", job_id, retries, MAX_RETRIES, error_msg)

            if retries < MAX_RETRIES:
                # Exponential backoff then re-queue
                backoff = 2**retries
                logger.info("Retrying job %s in %ds", job_id, backoff)
                await asyncio.sleep(backoff)
                job["retries"] = retries
                await self._queue_svc.update_job_status(job_id, JobStatus.PENDING, retries=retries)
                await self._redis.lpush(QUEUE_KEY, json.dumps(job))
            else:
                # Send to dead letter queue
                logger.error("Job %s exceeded max retries — moving to dead letter queue", job_id)
                job["retries"] = retries
                job["error"] = error_msg
                await self._redis.lpush(DEAD_LETTER_KEY, json.dumps(job))
                await self._queue_svc.update_job_status(job_id, JobStatus.FAILED, error=error_msg, retries=retries)

    async def _execute_operation(self, operation: GitOperation, payload: dict[str, Any]) -> None:
        """Dispatch a git operation to the GitOpsService."""
        tenant_slug: str = payload.get("tenant_slug", "")
        app_slug: str = payload.get("app_slug", "")
        service_name: str = payload.get("service_name", "")

        match operation:
            case GitOperation.CREATE_FILE | GitOperation.UPDATE_FILE:
                values = payload.get("values")
                if values is None:
                    raise ValueError("payload.values is required for CREATE_FILE / UPDATE_FILE")

                if service_name:
                    await self._gitops.write_service_values(tenant_slug, service_name, values)
                elif app_slug:
                    await self._gitops.write_app_values(tenant_slug, app_slug, values)
                else:
                    raise ValueError("payload must contain app_slug or service_name")

            case GitOperation.DELETE_FILE:
                if service_name:
                    await self._gitops.delete_service(tenant_slug, service_name)
                elif app_slug:
                    await self._gitops.delete_app(tenant_slug, app_slug)
                elif tenant_slug and not app_slug and not service_name:
                    await self._gitops.delete_tenant(tenant_slug)
                else:
                    raise ValueError("payload must contain tenant_slug and optionally app_slug or service_name")

            case _:
                raise ValueError(f"Unknown operation: {operation}")


async def main() -> None:
    """Entry point when run as a standalone process."""
    import redis.asyncio as aioredis

    from app.config import settings

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    redis_client = aioredis.from_url(
        getattr(settings, "redis_url", "redis://localhost:6379/0"),
        decode_responses=False,
    )
    gitops = GitOpsService()
    worker = GitWorker(redis_client, gitops)

    try:
        await worker.run()
    finally:
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
