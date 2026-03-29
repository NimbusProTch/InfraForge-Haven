"""GDPR / AVG Compliance endpoints.

Implements:
- Art. 20 (Data Portability): GET  /tenants/{slug}/gdpr/export
- Art. 17 (Right to Erasure): POST /tenants/{slug}/gdpr/erase
- Art. 7  (Consent management): CRUD on /tenants/{slug}/gdpr/consent
- Data retention policy: GET/PATCH /tenants/{slug}/gdpr/retention
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select

from app.deps import CurrentUser, DBSession
from app.models.application import Application
from app.models.data_retention_policy import DataRetentionPolicy
from app.models.deployment import Deployment
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember
from app.models.user_consent import ConsentType, UserConsent
from app.schemas.gdpr import (
    ConsentGrant,
    ConsentResponse,
    DataExportResponse,
    ErasureRequest,
    ErasureResponse,
    RetentionPolicyResponse,
    RetentionPolicyUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/gdpr", tags=["gdpr"])


async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


# ---------------------------------------------------------------------------
# Consent management
# ---------------------------------------------------------------------------


@router.get("/consent", response_model=list[ConsentResponse])
async def list_consents(
    tenant_slug: str, db: DBSession, current_user: CurrentUser, user_id: str | None = None
) -> list[UserConsent]:
    """List all consent records for this tenant (optionally filtered by user_id)."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    stmt = select(UserConsent).where(UserConsent.tenant_id == tenant.id)
    if user_id:
        stmt = stmt.where(UserConsent.user_id == user_id)
    result = await db.execute(stmt.order_by(UserConsent.created_at.desc()))
    return list(result.scalars().all())


@router.post("/consent", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
async def grant_consent(
    tenant_slug: str, body: ConsentGrant, db: DBSession, current_user: CurrentUser, user_id: str = "anonymous"
) -> UserConsent:
    """Record a consent grant (GDPR Art. 7)."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    consent = UserConsent(
        tenant_id=tenant.id,
        user_id=user_id,
        consent_type=body.consent_type,
        granted=True,
        ip_address=body.ip_address,
        user_agent=body.user_agent,
        context=body.context,
    )
    db.add(consent)
    await db.commit()
    await db.refresh(consent)
    return consent


@router.delete("/consent/{consent_type}", status_code=status.HTTP_200_OK, response_model=ConsentResponse)
async def revoke_consent(
    tenant_slug: str, consent_type: ConsentType, db: DBSession, current_user: CurrentUser, user_id: str = "anonymous"
) -> UserConsent:
    """Revoke a consent type — creates a new revocation record (GDPR Art. 7(3))."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    revocation = UserConsent(
        tenant_id=tenant.id,
        user_id=user_id,
        consent_type=consent_type,
        granted=False,
        revoked_at=datetime.now(UTC),
        context="User-initiated revocation",
    )
    db.add(revocation)
    await db.commit()
    await db.refresh(revocation)
    return revocation


# ---------------------------------------------------------------------------
# Data retention policy
# ---------------------------------------------------------------------------


@router.get("/retention", response_model=RetentionPolicyResponse)
async def get_retention_policy(tenant_slug: str, db: DBSession, current_user: CurrentUser) -> DataRetentionPolicy:
    """Get the data retention policy for this tenant."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(select(DataRetentionPolicy).where(DataRetentionPolicy.tenant_id == str(tenant.id)))
    policy = result.scalar_one_or_none()
    if policy is None:
        # Create default policy on first access
        policy = DataRetentionPolicy(tenant_id=str(tenant.id))
        db.add(policy)
        await db.commit()
        await db.refresh(policy)
    return policy


@router.patch("/retention", response_model=RetentionPolicyResponse)
async def update_retention_policy(
    tenant_slug: str, body: RetentionPolicyUpdate, db: DBSession, current_user: CurrentUser
) -> DataRetentionPolicy:
    """Update the data retention policy for this tenant."""
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(select(DataRetentionPolicy).where(DataRetentionPolicy.tenant_id == str(tenant.id)))
    policy = result.scalar_one_or_none()
    if policy is None:
        policy = DataRetentionPolicy(tenant_id=str(tenant.id))
        db.add(policy)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(policy, field, value)

    await db.commit()
    await db.refresh(policy)
    return policy


# ---------------------------------------------------------------------------
# Data export (Art. 20 — portability)
# ---------------------------------------------------------------------------


@router.get("/export", response_model=DataExportResponse)
async def export_data(
    tenant_slug: str, db: DBSession, current_user: CurrentUser, user_id: str = "anonymous"
) -> DataExportResponse:
    """Export all data for this tenant as structured JSON (GDPR Art. 20)."""
    tenant = await _get_tenant_or_404(tenant_slug, db)

    # Applications
    apps_result = await db.execute(select(Application).where(Application.tenant_id == tenant.id))
    applications = [
        {
            "id": str(a.id),
            "slug": a.slug,
            "name": a.name,
            "repo_url": a.repo_url,
            "branch": a.branch,
            "created_at": a.created_at.isoformat(),
        }
        for a in apps_result.scalars().all()
    ]

    # Deployments
    dep_result = await db.execute(
        select(Deployment)
        .join(Application, Deployment.application_id == Application.id)
        .where(Application.tenant_id == tenant.id)
        .order_by(Deployment.created_at.desc())
        .limit(500)
    )
    deployments = [
        {
            "id": str(d.id),
            "application_id": str(d.application_id),
            "status": d.status.value if hasattr(d.status, "value") else str(d.status),
            "image_tag": d.image_tag,
            "created_at": d.created_at.isoformat(),
        }
        for d in dep_result.scalars().all()
    ]

    # Consents
    con_result = await db.execute(select(UserConsent).where(UserConsent.tenant_id == tenant.id))
    consents = [
        {
            "id": str(c.id),
            "user_id": c.user_id,
            "consent_type": c.consent_type.value,
            "granted": c.granted,
            "created_at": c.created_at.isoformat(),
        }
        for c in con_result.scalars().all()
    ]

    # Members
    mem_result = await db.execute(select(TenantMember).where(TenantMember.tenant_id == tenant.id))
    members = [
        {
            "id": str(m.id),
            "user_id": m.user_id,
            "email": m.email,
            "role": m.role.value,
            "created_at": m.created_at.isoformat(),
        }
        for m in mem_result.scalars().all()
    ]

    return DataExportResponse(
        exported_at=datetime.now(UTC),
        tenant_slug=tenant_slug,
        requesting_user_id=user_id,
        applications=applications,
        deployments=deployments,
        consents=consents,
        members=members,
    )


# ---------------------------------------------------------------------------
# Right to erasure (Art. 17)
# ---------------------------------------------------------------------------


@router.post("/erase", response_model=ErasureResponse)
async def erase_data(
    tenant_slug: str, body: ErasureRequest, db: DBSession, current_user: CurrentUser, user_id: str = "anonymous"
) -> ErasureResponse:
    """Erase all data for this tenant (GDPR Art. 17 — right to erasure).

    This permanently deletes all applications, deployments, consents, and members.
    The tenant record itself is also removed.
    Requires confirmation string 'ERASE MY DATA'.
    """
    if body.confirm != "ERASE MY DATA":
        raise HTTPException(
            status_code=400,
            detail="Confirmation string must be 'ERASE MY DATA'",
        )

    tenant = await _get_tenant_or_404(tenant_slug, db)
    tenant_id = tenant.id

    # Count before deletion for the response
    apps = await db.execute(select(Application).where(Application.tenant_id == tenant_id))
    app_list = list(apps.scalars().all())
    app_ids = [a.id for a in app_list]

    dep_count = 0
    if app_ids:
        deps = await db.execute(select(Deployment).where(Deployment.application_id.in_(app_ids)))
        dep_list = list(deps.scalars().all())
        dep_count = len(dep_list)
        await db.execute(delete(Deployment).where(Deployment.application_id.in_(app_ids)))

    await db.execute(delete(Application).where(Application.tenant_id == tenant_id))
    con_result = await db.execute(delete(UserConsent).where(UserConsent.tenant_id == tenant_id))
    mem_result = await db.execute(delete(TenantMember).where(TenantMember.tenant_id == tenant_id))
    ret_result = await db.execute(delete(DataRetentionPolicy).where(DataRetentionPolicy.tenant_id == str(tenant_id)))

    await db.delete(tenant)
    await db.commit()

    logger.info("GDPR erasure completed for tenant %s by user %s", tenant_slug, user_id)

    return ErasureResponse(
        erased_at=datetime.now(UTC),
        tenant_slug=tenant_slug,
        requesting_user_id=user_id,
        records_deleted={
            "applications": len(app_list),
            "deployments": dep_count,
            "consents": con_result.rowcount,
            "members": mem_result.rowcount,
            "retention_policies": ret_result.rowcount,
        },
    )
