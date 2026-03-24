from fastapi import APIRouter

from app.k8s.client import k8s_client

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/cluster")
async def health_cluster() -> dict:
    k8s_status = await k8s_client.health_check()
    overall = "ok" if k8s_status["status"] == "ok" else "degraded"
    return {"status": overall, "kubernetes": k8s_status}
