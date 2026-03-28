import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.deps import DBSession
from app.k8s.client import k8s_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — returns 200 if the process is alive."""
    return {"status": "ok"}


@router.get("/readiness")
async def readiness(db: DBSession) -> dict:
    """Readiness probe — checks DB connectivity and K8s availability.

    Returns 200 only when the API is fully ready to serve traffic.
    Returns 503 if the database is unavailable.
    """
    checks: dict[str, str] = {}

    # DB check — uses the injected session (supports test overrides)
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Readiness DB check failed: %s", exc)
        checks["database"] = "unavailable"

    # K8s check (non-critical — API runs without K8s)
    k8s_status = await k8s_client.health_check()
    checks["kubernetes"] = k8s_status["status"]

    if not db_ok:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})

    return {"status": "ready", "checks": checks}


@router.get("/health/cluster")
async def health_cluster() -> dict:
    """Cluster health — checks Kubernetes API server connectivity."""
    k8s_status = await k8s_client.health_check()
    overall = "ok" if k8s_status["status"] == "ok" else "degraded"
    return {"status": overall, "kubernetes": k8s_status}
