"""Organization + SSO endpoints (Sprint 9).

Covers:
- Organization CRUD (/organizations)
- Member management (/organizations/{slug}/members)
- SSO config (SAML/OIDC) (/organizations/{slug}/sso)
- Tenant membership (/organizations/{slug}/tenants)
- Billing aggregation summary (/organizations/{slug}/billing)
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DBSession
from app.models.organization import (
    Organization,
    OrganizationMember,
    OrgTenantMembership,
    SSOConfig,
)
from app.schemas.organization import (
    BillingSummaryResponse,
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    OrgMemberInvite,
    OrgMemberResponse,
    OrgMemberUpdate,
    OrgTenantAdd,
    OrgTenantResponse,
    SSOConfigCreate,
    SSOConfigResponse,
    SSOConfigUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations", tags=["organizations"])


async def _get_org_or_404(org_slug: str, db: DBSession) -> Organization:
    result = await db.execute(select(Organization).where(Organization.slug == org_slug))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


# ---------------------------------------------------------------------------
# Organization CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(db: DBSession) -> list[Organization]:
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    return list(result.scalars().all())


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(body: OrganizationCreate, db: DBSession) -> Organization:
    existing = await db.execute(select(Organization).where(Organization.slug == body.slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Organization '{body.slug}' already exists")

    org = Organization(slug=body.slug, name=body.name, plan=body.plan)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


@router.get("/{org_slug}", response_model=OrganizationResponse)
async def get_organization(org_slug: str, db: DBSession) -> Organization:
    return await _get_org_or_404(org_slug, db)


@router.patch("/{org_slug}", response_model=OrganizationResponse)
async def update_organization(org_slug: str, body: OrganizationUpdate, db: DBSession) -> Organization:
    org = await _get_org_or_404(org_slug, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return org


@router.delete("/{org_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(org_slug: str, db: DBSession) -> None:
    org = await _get_org_or_404(org_slug, db)
    await db.delete(org)
    await db.commit()


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


@router.get("/{org_slug}/members", response_model=list[OrgMemberResponse])
async def list_members(org_slug: str, db: DBSession) -> list[OrganizationMember]:
    org = await _get_org_or_404(org_slug, db)
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == org.id)
        .order_by(OrganizationMember.created_at)
    )
    return list(result.scalars().all())


@router.post("/{org_slug}/members", response_model=OrgMemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(org_slug: str, body: OrgMemberInvite, db: DBSession) -> OrganizationMember:
    org = await _get_org_or_404(org_slug, db)

    # Prevent duplicate membership
    existing = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="User is already a member of this organization")

    member = OrganizationMember(
        organization_id=org.id,
        user_id=body.user_id,
        email=body.email,
        display_name=body.display_name,
        role=body.role,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.patch("/{org_slug}/members/{user_id}", response_model=OrgMemberResponse)
async def update_member_role(org_slug: str, user_id: str, body: OrgMemberUpdate, db: DBSession) -> OrganizationMember:
    org = await _get_org_or_404(org_slug, db)
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    member.role = body.role
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/{org_slug}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(org_slug: str, user_id: str, db: DBSession) -> None:
    org = await _get_org_or_404(org_slug, db)
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.delete(member)
    await db.commit()


# ---------------------------------------------------------------------------
# SSO config (SAML / OIDC)
# ---------------------------------------------------------------------------


@router.get("/{org_slug}/sso", response_model=list[SSOConfigResponse])
async def list_sso_configs(org_slug: str, db: DBSession) -> list[SSOConfig]:
    org = await _get_org_or_404(org_slug, db)
    result = await db.execute(
        select(SSOConfig)
        .where(SSOConfig.organization_id == org.id)
        .order_by(SSOConfig.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{org_slug}/sso", response_model=SSOConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_sso_config(org_slug: str, body: SSOConfigCreate, db: DBSession) -> SSOConfig:
    org = await _get_org_or_404(org_slug, db)

    if body.sso_type.value == "oidc" and not body.discovery_url:
        raise HTTPException(status_code=400, detail="discovery_url is required for OIDC SSO")
    if body.sso_type.value == "saml" and not (body.metadata_url or body.metadata_xml):
        raise HTTPException(status_code=400, detail="metadata_url or metadata_xml is required for SAML SSO")

    sso = SSOConfig(
        organization_id=org.id,
        sso_type=body.sso_type,
        client_id=body.client_id,
        client_secret=body.client_secret,
        discovery_url=body.discovery_url,
        metadata_url=body.metadata_url,
        metadata_xml=body.metadata_xml,
        sso_only=body.sso_only,
    )
    db.add(sso)
    await db.commit()
    await db.refresh(sso)
    return sso


@router.patch("/{org_slug}/sso/{sso_id}", response_model=SSOConfigResponse)
async def update_sso_config(org_slug: str, sso_id: str, body: SSOConfigUpdate, db: DBSession) -> SSOConfig:
    org = await _get_org_or_404(org_slug, db)
    result = await db.execute(
        select(SSOConfig).where(SSOConfig.organization_id == org.id, SSOConfig.id == sso_id)
    )
    sso = result.scalar_one_or_none()
    if sso is None:
        raise HTTPException(status_code=404, detail="SSO config not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(sso, field, value)
    await db.commit()
    await db.refresh(sso)
    return sso


@router.delete("/{org_slug}/sso/{sso_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sso_config(org_slug: str, sso_id: str, db: DBSession) -> None:
    org = await _get_org_or_404(org_slug, db)
    result = await db.execute(
        select(SSOConfig).where(SSOConfig.organization_id == org.id, SSOConfig.id == sso_id)
    )
    sso = result.scalar_one_or_none()
    if sso is None:
        raise HTTPException(status_code=404, detail="SSO config not found")
    await db.delete(sso)
    await db.commit()


# ---------------------------------------------------------------------------
# Tenant membership in org
# ---------------------------------------------------------------------------


@router.get("/{org_slug}/tenants", response_model=list[OrgTenantResponse])
async def list_org_tenants(org_slug: str, db: DBSession) -> list[OrgTenantMembership]:
    org = await _get_org_or_404(org_slug, db)
    result = await db.execute(
        select(OrgTenantMembership).where(OrgTenantMembership.organization_id == org.id)
    )
    return list(result.scalars().all())


@router.post("/{org_slug}/tenants", response_model=OrgTenantResponse, status_code=status.HTTP_201_CREATED)
async def add_tenant_to_org(org_slug: str, body: OrgTenantAdd, db: DBSession) -> OrgTenantMembership:
    org = await _get_org_or_404(org_slug, db)

    # Prevent duplicate
    existing = await db.execute(
        select(OrgTenantMembership).where(
            OrgTenantMembership.organization_id == org.id,
            OrgTenantMembership.tenant_id == body.tenant_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Tenant is already in this organization")

    membership = OrgTenantMembership(organization_id=org.id, tenant_id=body.tenant_id)
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership


@router.delete("/{org_slug}/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tenant_from_org(org_slug: str, tenant_id: str, db: DBSession) -> None:
    org = await _get_org_or_404(org_slug, db)
    result = await db.execute(
        select(OrgTenantMembership).where(
            OrgTenantMembership.organization_id == org.id,
            OrgTenantMembership.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Tenant not in this organization")
    await db.delete(membership)
    await db.commit()


# ---------------------------------------------------------------------------
# Billing aggregation summary
# ---------------------------------------------------------------------------


@router.get("/{org_slug}/billing", response_model=BillingSummaryResponse)
async def billing_summary(org_slug: str, db: DBSession) -> BillingSummaryResponse:
    """Return billing aggregation summary for the organization."""
    org = await _get_org_or_404(org_slug, db)
    tenant_count_result = await db.execute(
        select(OrgTenantMembership).where(OrgTenantMembership.organization_id == org.id)
    )
    tenant_count = len(list(tenant_count_result.scalars().all()))

    return BillingSummaryResponse(
        organization_id=org.id,
        organization_slug=org.slug,
        plan=org.plan,
        tenant_count=tenant_count,
        stripe_customer_id=org.stripe_customer_id,
        stripe_subscription_id=org.stripe_subscription_id,
    )
