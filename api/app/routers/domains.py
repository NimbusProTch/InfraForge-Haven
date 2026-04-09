"""Custom domain management endpoints.

Routes:
  POST   /tenants/{tenant_slug}/apps/{app_slug}/domains          — add custom domain
  GET    /tenants/{tenant_slug}/apps/{app_slug}/domains          — list domains
  GET    /tenants/{tenant_slug}/apps/{app_slug}/domains/{domain} — domain detail
  POST   /tenants/{tenant_slug}/apps/{app_slug}/domains/{domain}/verify — trigger DNS check
  DELETE /tenants/{tenant_slug}/apps/{app_slug}/domains/{domain} — remove domain

  POST   /domains/wildcard — issue wildcard cert for platform (admin)

H3e (P2.5 / P18 batch 2): migrated to canonical `TenantMembership`
dependency from `app/deps.py`. The local `_get_tenant_or_404` helper has
been removed. The platform-level wildcard cert route still uses
`current_user` because it has no tenant_slug path param.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DBSession, K8sDep, TenantMembership
from app.models.application import Application
from app.models.domain import CertificateStatus, DomainVerification
from app.schemas.domain import DomainCreate, DomainResponse, DomainVerifyResponse, WildcardCertRequest
from app.services.domain_service import (
    CertManagerService,
    add_custom_domain_to_httproute,
    get_lb_hostname,
    remove_custom_domain_from_httproute,
    sync_certificate_status,
    verify_dns_ownership,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["domains"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_app_or_404(tenant_id: object, app_slug: str, db: DBSession) -> Application:
    result = await db.execute(
        select(Application).where(
            Application.tenant_id == tenant_id,
            Application.slug == app_slug,
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return app


async def _get_domain_or_404(app_id: object, domain_str: str, db: DBSession) -> DomainVerification:
    result = await db.execute(
        select(DomainVerification).where(
            DomainVerification.application_id == app_id,
            DomainVerification.domain == domain_str,
        )
    )
    domain = result.scalar_one_or_none()
    if domain is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    return domain


def _to_response(domain: DomainVerification) -> DomainResponse:
    return DomainResponse.from_orm_with_instructions(domain, get_lb_hostname())


# ---------------------------------------------------------------------------
# Per-app domain routes
# ---------------------------------------------------------------------------

app_domains_router = APIRouter(prefix="/tenants/{tenant_slug}/apps/{app_slug}/domains")


@app_domains_router.post("", response_model=DomainResponse, status_code=status.HTTP_201_CREATED)
async def add_domain(
    tenant_slug: str,
    app_slug: str,
    body: DomainCreate,
    db: DBSession,
    k8s: K8sDep,  # noqa: ARG001 — kept on signature for parity with other routes; cert issuance happens via verify
    tenant: TenantMembership,
) -> DomainResponse:
    """Add a custom domain to an application.

    Returns the DNS verification instructions the user needs to follow.
    The domain is NOT yet active — the user must verify DNS ownership first.
    """
    app = await _get_app_or_404(tenant.id, app_slug, db)

    # Check for duplicates across all applications (domain must be globally unique)
    existing = await db.execute(select(DomainVerification).where(DomainVerification.domain == body.domain))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Domain '{body.domain}' is already registered",
        )

    domain = DomainVerification(application_id=app.id, domain=body.domain)
    db.add(domain)
    await db.commit()
    await db.refresh(domain)

    logger.info("Domain added: %s → app=%s tenant=%s", body.domain, app_slug, tenant_slug)
    return _to_response(domain)


@app_domains_router.get("", response_model=list[DomainResponse])
async def list_domains(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    db: DBSession,
    k8s: K8sDep,  # noqa: ARG001 — kept for parity with mutating routes
    tenant: TenantMembership,
) -> list[DomainResponse]:
    """List all custom domains for an application."""
    app = await _get_app_or_404(tenant.id, app_slug, db)

    result = await db.execute(
        select(DomainVerification)
        .where(DomainVerification.application_id == app.id)
        .order_by(DomainVerification.created_at.desc())
    )
    domains = list(result.scalars().all())
    return [_to_response(d) for d in domains]


@app_domains_router.get("/{domain}", response_model=DomainResponse)
async def get_domain(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    domain: str,
    db: DBSession,
    k8s: K8sDep,  # noqa: ARG001 — kept for parity
    tenant: TenantMembership,
) -> DomainResponse:
    """Get details for a specific custom domain."""
    app = await _get_app_or_404(tenant.id, app_slug, db)
    domain_record = await _get_domain_or_404(app.id, domain, db)
    return _to_response(domain_record)


@app_domains_router.post("/{domain}/verify", response_model=DomainVerifyResponse)
async def verify_domain(
    tenant_slug: str,
    app_slug: str,
    domain: str,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
) -> DomainVerifyResponse:
    """Trigger DNS ownership verification for a domain.

    Checks the TXT record `_haven-verify.{domain}` = `{verification_token}`.
    If verified, kicks off cert-manager certificate issuance and updates the HTTPRoute.
    """
    app = await _get_app_or_404(tenant.id, app_slug, db)
    domain_record = await _get_domain_or_404(app.id, domain, db)

    result = await verify_dns_ownership(domain_record)

    if result.verified:
        from datetime import UTC, datetime

        domain_record.verified_at = datetime.now(UTC)
        domain_record.certificate_status = CertificateStatus.issuing

        # Issue Let's Encrypt certificate
        cert_svc = CertManagerService(k8s)
        try:
            tls_secret = await cert_svc.issue_custom_domain_cert(
                domain=domain_record.domain,
                namespace=tenant.namespace,
            )
            # Add domain to HTTPRoute
            await add_custom_domain_to_httproute(
                k8s=k8s,
                namespace=tenant.namespace,
                app_slug=app_slug,
                custom_domain=domain_record.domain,
                tenant_slug=tenant_slug,
                tls_secret_name=tls_secret,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cert/HTTPRoute update failed after domain verify: %s", exc)
            domain_record.certificate_status = CertificateStatus.failed
            domain_record.certificate_error = str(exc)

        await db.commit()
        await db.refresh(domain_record)

    return DomainVerifyResponse(
        verified=result.verified,
        message=result.message,
        certificate_status=domain_record.certificate_status,
    )


@app_domains_router.post("/{domain}/sync-cert", response_model=DomainResponse)
async def sync_cert_status(
    tenant_slug: str,  # noqa: ARG001 — used by TenantMembership dep, kept for OpenAPI
    app_slug: str,
    domain: str,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
) -> DomainResponse:
    """Sync the cert-manager Certificate status from the cluster into the DB."""
    app = await _get_app_or_404(tenant.id, app_slug, db)
    domain_record = await _get_domain_or_404(app.id, domain, db)

    new_status = await sync_certificate_status(
        domain_record=domain_record,
        app_namespace=tenant.namespace,
        k8s=k8s,
    )
    domain_record.certificate_status = new_status
    await db.commit()
    await db.refresh(domain_record)

    return _to_response(domain_record)


@app_domains_router.delete("/{domain}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_domain(
    tenant_slug: str,
    app_slug: str,
    domain: str,
    db: DBSession,
    k8s: K8sDep,
    tenant: TenantMembership,
) -> None:
    """Remove a custom domain from an application.

    Deletes the cert-manager Certificate, removes the hostname from HTTPRoute,
    then deletes the DB record.
    """
    app = await _get_app_or_404(tenant.id, app_slug, db)
    domain_record = await _get_domain_or_404(app.id, domain, db)

    # Remove from HTTPRoute first
    await remove_custom_domain_from_httproute(
        k8s=k8s,
        namespace=tenant.namespace,
        app_slug=app_slug,
        custom_domain=domain_record.domain,
    )

    # Delete cert-manager Certificate
    cert_svc = CertManagerService(k8s)
    await cert_svc.delete_cert(namespace=tenant.namespace, domain=domain_record.domain)

    await db.delete(domain_record)
    await db.commit()

    logger.info("Domain deleted: %s from app=%s tenant=%s", domain, app_slug, tenant_slug)


# ---------------------------------------------------------------------------
# Platform-level wildcard cert (admin operation)
# ---------------------------------------------------------------------------

platform_router = APIRouter(prefix="/platform/domains")


@platform_router.post("/wildcard-cert", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def issue_wildcard_cert(
    body: WildcardCertRequest,
    k8s: K8sDep,
    current_user: CurrentUser,
) -> dict:
    """Issue a wildcard TLS certificate for *.apps.{platform_domain}.

    Requires a DNS-01 ClusterIssuer (Cloudflare) named 'letsencrypt-dns' in the cluster.
    This is an admin operation — add auth guard before exposing publicly.
    """
    cert_svc = CertManagerService(k8s)
    secret_name = await cert_svc.issue_wildcard_cert(platform_domain=body.platform_domain)
    return {
        "status": "accepted",
        "platform_domain": body.platform_domain,
        "wildcard_domain": f"*.apps.{body.platform_domain}",
        "tls_secret_name": secret_name,
        "message": ("Wildcard certificate issuance started. Check cert-manager logs for DNS-01 challenge progress."),
    }


# Combine into one router that main.py imports
router.include_router(app_domains_router)
router.include_router(platform_router)
