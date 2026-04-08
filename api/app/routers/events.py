"""SSE endpoints for real-time lifecycle events.

Provides Server-Sent Events streams for tenant, service, and app operations.
UI connects via EventSource to receive step-by-step progress updates.

Usage (browser):
    const es = new EventSource('/api/v1/tenants/rotterdam/events');
    es.addEventListener('step', (e) => { console.log(JSON.parse(e.data)); });
    es.addEventListener('done', (e) => { es.close(); });

H0-11: All three streams previously had NO authentication AT ALL (no
CurrentUser dep, no DB lookup, no membership check). Any unauthenticated
network actor could subscribe to any tenant's lifecycle bus and watch
provisioning steps including service names, error messages, and
credential metadata. Now requires JWT + tenant membership.
"""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.deps import CurrentUser, DBSession
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember
from app.services.lifecycle_events import lifecycle_bus

router = APIRouter(tags=["events"])


async def _require_tenant_member(tenant_slug: str, db: DBSession, current_user: dict) -> None:
    """Verify the caller is a member of the tenant. 404 if missing, 403 if not member."""
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    user_id = current_user.get("sub", "")
    member_q = await db.execute(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant.id,
            TenantMember.user_id == user_id,
        )
    )
    if member_q.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this tenant",
        )


@router.get("/tenants/{tenant_slug}/events")
async def tenant_events(
    tenant_slug: str,
    request: Request,
    db: DBSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    """Stream tenant lifecycle events (provision/deprovision steps)."""
    await _require_tenant_member(tenant_slug, db, current_user)
    key = f"tenant:{tenant_slug}"
    last_id = int(request.headers.get("Last-Event-ID", "0"))

    async def _generate():
        async for chunk in lifecycle_bus.stream(key, last_event_id=last_id):
            yield chunk

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.get("/tenants/{tenant_slug}/services/{service_name}/events")
async def service_events(
    tenant_slug: str,
    service_name: str,
    request: Request,
    db: DBSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    """Stream service lifecycle events (provision/ready/deprovision steps)."""
    await _require_tenant_member(tenant_slug, db, current_user)
    key = f"service:{tenant_slug}:{service_name}"
    last_id = int(request.headers.get("Last-Event-ID", "0"))

    async def _generate():
        async for chunk in lifecycle_bus.stream(key, last_event_id=last_id):
            yield chunk

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.get("/tenants/{tenant_slug}/apps/{app_slug}/lifecycle-events")
async def app_events(
    tenant_slug: str,
    app_slug: str,
    request: Request,
    db: DBSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    """Stream app lifecycle events (create/build/deploy steps)."""
    await _require_tenant_member(tenant_slug, db, current_user)
    key = f"app:{tenant_slug}:{app_slug}"
    last_id = int(request.headers.get("Last-Event-ID", "0"))

    async def _generate():
        async for chunk in lifecycle_bus.stream(key, last_event_id=last_id):
            yield chunk

    return StreamingResponse(_generate(), media_type="text/event-stream")
