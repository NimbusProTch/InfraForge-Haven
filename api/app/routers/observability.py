"""Observability endpoints: pod status, resource metrics, and K8s events."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import CurrentUser, DBSession, K8sDep
from app.models.application import Application
from app.models.tenant import Tenant

router = APIRouter(prefix="/tenants/{tenant_slug}/apps/{app_slug}", tags=["observability"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PodInfo(BaseModel):
    name: str
    status: str  # Running | Pending | CrashLoopBackOff | Error | Terminated | Unknown
    restarts: int
    age: str
    cpu_value: str | None = None  # e.g. "42m"
    memory_value: str | None = None  # e.g. "128Mi"
    cpu_usage: int | None = None  # percent of limit (0-100), None if no limit configured
    memory_usage: int | None = None  # percent of limit (0-100), None if no limit configured
    node: str | None = None


class AppEvent(BaseModel):
    reason: str
    message: str
    type: str  # Normal | Warning
    count: int
    first_time: datetime | None = None
    last_time: datetime | None = None
    object_name: str


class PodsResponse(BaseModel):
    pods: list[PodInfo]
    k8s_available: bool


class EventsResponse(BaseModel):
    events: list[AppEvent]
    k8s_available: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_age(created_at) -> str:  # type: ignore[return]
    """Convert a kubernetes datetime to a human-readable age string."""
    if created_at is None:
        return "unknown"
    try:
        if hasattr(created_at, "tzinfo") and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        now = datetime.now(tz=UTC)
        delta = now - created_at
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        if seconds < 86400:
            return f"{seconds // 3600}h"
        return f"{seconds // 86400}d"
    except Exception:  # noqa: BLE001
        return "unknown"


def _parse_cpu_millicores(cpu_str: str | None) -> int | None:
    """Parse a CPU quantity string (e.g. '42m', '0.5') to millicores."""
    if not cpu_str:
        return None
    try:
        if cpu_str.endswith("m"):
            return int(cpu_str[:-1])
        return int(float(cpu_str) * 1000)
    except (ValueError, TypeError):
        return None


def _parse_memory_bytes(mem_str: str | None) -> int | None:
    """Parse a memory quantity string (e.g. '128Mi', '1Gi', '131072Ki') to bytes."""
    if not mem_str:
        return None
    try:
        units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4, "k": 1000, "M": 1000**2, "G": 1000**3}
        for suffix, multiplier in units.items():
            if mem_str.endswith(suffix):
                return int(mem_str[: -len(suffix)]) * multiplier
        return int(mem_str)
    except (ValueError, TypeError):
        return None


def _bytes_to_mib(n: int) -> str:
    return f"{round(n / (1024**2))}Mi"


async def _get_tenant_or_404(tenant_slug: str, db: DBSession, current_user: dict) -> Tenant:
    """H0-9: Lock pod/log/metric data to tenant members."""
    # Local import to avoid widening the file's import set unnecessarily.
    from app.models.tenant_member import TenantMember

    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    user_id = current_user.get("sub", "")
    member_q = await db.execute(
        select(TenantMember).where(TenantMember.tenant_id == tenant.id, TenantMember.user_id == user_id)
    )
    if member_q.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="You are not a member of this tenant")
    return tenant


async def _get_app_or_404(tenant_id: uuid.UUID, app_slug: str, db: DBSession) -> Application:
    result = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant_id,
            Application.slug == app_slug,
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/pods", response_model=PodsResponse)
async def get_pods(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> PodsResponse:
    """Return pod status and resource metrics for an application.

    Fetches pod list from CoreV1Api and CPU/memory usage from the
    Kubernetes metrics-server (metrics.k8s.io/v1beta1).  When the cluster
    is unavailable the response still returns successfully with an empty
    pod list and ``k8s_available=False``.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    app = await _get_app_or_404(tenant.id, app_slug, db)
    namespace = tenant.namespace
    label_selector = f"app={app.slug}"

    if not k8s.is_available():
        return PodsResponse(pods=[], k8s_available=False)

    # Fetch pods
    try:
        pod_list = await asyncio.to_thread(
            k8s.core_v1.list_namespaced_pod,
            namespace=namespace,
            label_selector=label_selector,
        )
    except Exception as exc:
        logger.warning("Failed to list pods for %s/%s: %s", namespace, app_slug, exc)
        return PodsResponse(pods=[], k8s_available=True)

    # Fetch metrics (best-effort — metrics-server may not be running)
    metrics_by_pod: dict[str, dict] = {}
    try:
        metrics_result = await asyncio.to_thread(
            k8s.custom_objects.list_namespaced_custom_object,
            group="metrics.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="pods",
            label_selector=label_selector,
        )
        for item in metrics_result.get("items", []):
            pod_name = item["metadata"]["name"]
            containers = item.get("containers", [])
            if containers:
                # Sum across all containers in the pod
                total_cpu_mc = sum((_parse_cpu_millicores(c["usage"].get("cpu")) or 0) for c in containers)
                total_mem_b = sum((_parse_memory_bytes(c["usage"].get("memory")) or 0) for c in containers)
                metrics_by_pod[pod_name] = {
                    "cpu_mc": total_cpu_mc,
                    "mem_bytes": total_mem_b,
                }
    except Exception as exc:  # noqa: BLE001
        logger.debug("metrics-server unavailable: %s", exc)

    # Parse resource limits from the app model (used for % calculation)
    cpu_limit_mc = _parse_cpu_millicores(app.resource_cpu_limit)
    mem_limit_bytes = _parse_memory_bytes(app.resource_memory_limit)

    pods: list[PodInfo] = []
    for pod in pod_list.items:
        pod_name: str = pod.metadata.name
        phase: str = pod.status.phase or "Unknown"

        # Determine a richer status string (CrashLoopBackOff, etc.)
        display_status = phase
        restart_count = 0
        if pod.status.container_statuses:
            cs = pod.status.container_statuses[0]
            restart_count = cs.restart_count or 0
            if cs.state:
                if cs.state.waiting and cs.state.waiting.reason:
                    display_status = cs.state.waiting.reason
                elif cs.state.terminated and cs.state.terminated.reason:
                    display_status = cs.state.terminated.reason

        age = _format_age(pod.metadata.creation_timestamp)
        node = pod.spec.node_name

        # Metrics
        m = metrics_by_pod.get(pod_name)
        cpu_value: str | None = None
        memory_value: str | None = None
        cpu_usage: int | None = None
        memory_usage: int | None = None

        if m:
            cpu_mc = m["cpu_mc"]
            mem_bytes = m["mem_bytes"]
            cpu_value = f"{cpu_mc}m"
            memory_value = _bytes_to_mib(mem_bytes)
            if cpu_limit_mc and cpu_limit_mc > 0:
                cpu_usage = min(100, round(cpu_mc / cpu_limit_mc * 100))
            if mem_limit_bytes and mem_limit_bytes > 0:
                memory_usage = min(100, round(mem_bytes / mem_limit_bytes * 100))

        pods.append(
            PodInfo(
                name=pod_name,
                status=display_status,
                restarts=restart_count,
                age=age,
                cpu_value=cpu_value,
                memory_value=memory_value,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                node=node,
            )
        )

    return PodsResponse(pods=pods, k8s_available=True)


@router.get("/events", response_model=EventsResponse)
async def get_events(
    tenant_slug: str,
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,
    current_user: CurrentUser,
    limit: int = 20,
) -> EventsResponse:
    """Return recent K8s events for an application (pods + deployment).

    Queries events in the tenant namespace filtered to objects whose name
    starts with the app slug.  Returns the most recent ``limit`` events,
    newest first.
    """
    tenant = await _get_tenant_or_404(tenant_slug, db, current_user)
    app = await _get_app_or_404(tenant.id, app_slug, db)
    namespace = tenant.namespace

    if not k8s.is_available():
        return EventsResponse(events=[], k8s_available=False)

    try:
        event_list = await asyncio.to_thread(
            k8s.core_v1.list_namespaced_event,
            namespace=namespace,
        )
    except Exception as exc:
        logger.warning("Failed to list events for %s/%s: %s", namespace, app_slug, exc)
        return EventsResponse(events=[], k8s_available=True)

    app_events: list[AppEvent] = []
    for ev in event_list.items:
        obj_name: str = ev.involved_object.name or ""
        # Include events for any K8s object whose name starts with the app slug
        if not obj_name.startswith(app.slug):
            continue

        first_time = ev.first_timestamp
        last_time = ev.last_timestamp
        if first_time and hasattr(first_time, "tzinfo") and first_time.tzinfo is None:
            first_time = first_time.replace(tzinfo=UTC)
        if last_time and hasattr(last_time, "tzinfo") and last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=UTC)

        app_events.append(
            AppEvent(
                reason=ev.reason or "",
                message=ev.message or "",
                type=ev.type or "Normal",
                count=ev.count or 1,
                first_time=first_time,
                last_time=last_time,
                object_name=obj_name,
            )
        )

    # Sort newest first (by last_time, fall back to first_time)
    def _sort_key(e: AppEvent):
        return e.last_time or e.first_time or datetime.min.replace(tzinfo=UTC)

    app_events.sort(key=_sort_key, reverse=True)

    return EventsResponse(events=app_events[:limit], k8s_available=True)
