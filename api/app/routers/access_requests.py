"""Enterprise access-request funnel.

Flow
----
1. Unauthenticated visitor lands on /auth/request-access
2. UI POSTs to this router (no auth header, rate-limited, honeypot)
3. Row inserted with status=pending, email to platform admins
4. Platform admin reviews in /admin/access-requests (this router)
5. Approve → /admin/tenants/provision (separate router) does the work
6. PATCH flips status to approved/rejected with reviewer stamp

No self-signup. No implicit user-create. The row is inert — approval is
an explicit admin action in ET3 (admin_tenants router).
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.deps import DBSession, PlatformAdminUser
from app.models.access_request import AccessRequest, AccessRequestStatus
from app.rate_limit import RATE_ACCESS_REQUEST, limiter
from app.schemas.access_request import (
    HONEYPOT_FIELD,
    AccessRequestCreate,
    AccessRequestResponse,
    AccessRequestReview,
)

router = APIRouter(prefix="/access-requests", tags=["access-requests"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Anonymous submission
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_ACCESS_REQUEST)
async def submit_access_request(
    request: Request,
    body: AccessRequestCreate,
    db: DBSession,
) -> dict:
    """Anonymous submission of an access request.

    No authentication required — public form. Protections in place:
    - slowapi rate limit (``RATE_ACCESS_REQUEST`` = 5/hour per IP)
    - honeypot ``website`` field must be empty (bots fill it)
    - email validation (Pydantic ``EmailStr`` + disposable-domain blocklist)
    - submitter IP is stored for audit but nothing else is correlated
    """
    # Honeypot: if populated, it's a bot. Silently succeed so the bot
    # thinks it worked (avoid giving it a 4xx signal to retune).
    honeypot = getattr(body, HONEYPOT_FIELD, None)
    if honeypot:
        logger.info(
            "access-request honeypot tripped from %s (email=%s)",
            request.client.host if request.client else "?",
            body.email,
        )
        return {"status": "received"}

    ip = request.client.host if request.client else None

    ar = AccessRequest(
        name=body.name,
        email=str(body.email),
        org_name=body.org_name,
        message=body.message,
        status=AccessRequestStatus.PENDING,
        submitter_ip=ip,
    )
    db.add(ar)
    await db.commit()
    await db.refresh(ar)

    logger.info(
        "access-request submitted: id=%s email=%s org=%s ip=%s",
        ar.id,
        ar.email,
        ar.org_name,
        ip,
    )
    # Intentionally return a minimal body — no id, no timing info. The
    # UI shows a generic "thank you" screen. This prevents an attacker
    # from enumerating request IDs.
    return {"status": "received"}


# ---------------------------------------------------------------------------
# Platform-admin review
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AccessRequestResponse])
async def list_access_requests(
    db: DBSession,
    current_user: PlatformAdminUser,  # noqa: ARG001 — role guard
    status_filter: AccessRequestStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
) -> list[AccessRequest]:
    """Platform-admin only. List pending/approved/rejected access requests."""
    stmt = select(AccessRequest).order_by(AccessRequest.created_at.desc()).limit(limit)
    if status_filter is not None:
        stmt = stmt.where(AccessRequest.status == status_filter)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{request_id}", response_model=AccessRequestResponse)
async def get_access_request(
    request_id: uuid.UUID,
    db: DBSession,
    current_user: PlatformAdminUser,  # noqa: ARG001
) -> AccessRequest:
    result = await db.execute(select(AccessRequest).where(AccessRequest.id == request_id))
    ar = result.scalar_one_or_none()
    if ar is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    return ar


@router.patch("/{request_id}", response_model=AccessRequestResponse)
async def review_access_request(
    request_id: uuid.UUID,
    body: AccessRequestReview,
    db: DBSession,
    current_user: PlatformAdminUser,
) -> AccessRequest:
    """Approve or reject an access request.

    This does NOT provision the user — approval is just a bookkeeping
    flip. The actual Keycloak user + tenant + membership creation lives
    in the ``/admin/tenants/provision`` endpoint (ET3). Separating them
    means an admin can reject a spammy request without any side effects,
    and can re-run provisioning if the first attempt fails.
    """
    result = await db.execute(select(AccessRequest).where(AccessRequest.id == request_id))
    ar = result.scalar_one_or_none()
    if ar is None:
        raise HTTPException(status_code=404, detail="Access request not found")

    if ar.status != AccessRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Access request already reviewed (status={ar.status.value})",
        )

    ar.status = body.status
    ar.reviewed_by = current_user.get("sub", "")
    ar.reviewed_at = datetime.now(UTC)
    ar.review_notes = body.review_notes

    await db.commit()
    await db.refresh(ar)
    logger.info(
        "access-request %s reviewed: status=%s by=%s",
        ar.id,
        ar.status.value,
        ar.reviewed_by,
    )
    return ar
