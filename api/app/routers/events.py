"""SSE endpoints for real-time lifecycle events.

Provides Server-Sent Events streams for tenant, service, and app operations.
UI connects via EventSource to receive step-by-step progress updates.

Usage (browser):
    const es = new EventSource('/api/v1/tenants/rotterdam/events');
    es.addEventListener('step', (e) => { console.log(JSON.parse(e.data)); });
    es.addEventListener('done', (e) => { es.close(); });
"""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.lifecycle_events import lifecycle_bus

router = APIRouter(tags=["events"])


@router.get("/tenants/{tenant_slug}/events")
async def tenant_events(tenant_slug: str, request: Request) -> StreamingResponse:
    """Stream tenant lifecycle events (provision/deprovision steps)."""
    key = f"tenant:{tenant_slug}"
    last_id = int(request.headers.get("Last-Event-ID", "0"))

    async def _generate():
        async for chunk in lifecycle_bus.stream(key, last_event_id=last_id):
            yield chunk

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.get("/tenants/{tenant_slug}/services/{service_name}/events")
async def service_events(tenant_slug: str, service_name: str, request: Request) -> StreamingResponse:
    """Stream service lifecycle events (provision/ready/deprovision steps)."""
    key = f"service:{tenant_slug}:{service_name}"
    last_id = int(request.headers.get("Last-Event-ID", "0"))

    async def _generate():
        async for chunk in lifecycle_bus.stream(key, last_event_id=last_id):
            yield chunk

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.get("/tenants/{tenant_slug}/apps/{app_slug}/lifecycle-events")
async def app_events(tenant_slug: str, app_slug: str, request: Request) -> StreamingResponse:
    """Stream app lifecycle events (create/build/deploy steps)."""
    key = f"app:{tenant_slug}:{app_slug}"
    last_id = int(request.headers.get("Last-Event-ID", "0"))

    async def _generate():
        async for chunk in lifecycle_bus.stream(key, last_event_id=last_id):
            yield chunk

    return StreamingResponse(_generate(), media_type="text/event-stream")
