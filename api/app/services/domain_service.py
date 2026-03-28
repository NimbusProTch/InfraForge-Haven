"""Custom domain management service.

Handles DNS ownership verification (TXT record) and cert-manager Certificate CRD lifecycle.
"""
import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime

import dns.exception
import dns.resolver

from app.config import settings
from app.k8s.client import K8sClient
from app.models.domain import CertificateStatus, DomainVerification

logger = logging.getLogger(__name__)

# cert-manager API coordinates
_CERT_MANAGER_GROUP = "cert-manager.io"
_CERT_MANAGER_VERSION = "v1"
_CERT_MANAGER_PLURAL_CERTS = "certificates"
_CERT_MANAGER_PLURAL_ISSUERS = "clusterissuers"

# Default ClusterIssuer names — must exist in the cluster
LETSENCRYPT_HTTP_ISSUER = "letsencrypt-http"
LETSENCRYPT_DNS_ISSUER = "letsencrypt-dns"


# ---------------------------------------------------------------------------
# DNS helpers
# ---------------------------------------------------------------------------


def _txt_record_name(domain: str) -> str:
    return f"_haven-verify.{domain}"


def _app_hostname(tenant_slug: str, app_slug: str) -> str:
    return f"{app_slug}.{tenant_slug}.apps.{settings.lb_ip}.sslip.io"


def _cert_secret_name(domain: str) -> str:
    """K8s Secret name for the certificate TLS data."""
    safe = re.sub(r"[^a-z0-9-]", "-", domain.lower())
    return f"custom-domain-tls-{safe}"


# ---------------------------------------------------------------------------
# DNS Verification
# ---------------------------------------------------------------------------


class DnsVerificationResult:
    def __init__(self, *, verified: bool, message: str) -> None:
        self.verified = verified
        self.message = message


def _resolve_txt(name: str) -> list[str]:
    """Resolve TXT records for *name*. Returns list of string values."""
    try:
        answers = dns.resolver.resolve(name, "TXT")
        return [rdata.to_text().strip('"') for rdata in answers]
    except dns.resolver.NXDOMAIN:
        return []
    except dns.resolver.NoAnswer:
        return []
    except dns.exception.DNSException as exc:
        logger.debug("DNS TXT lookup failed for %s: %s", name, exc)
        return []


def _resolve_cname(name: str) -> str | None:
    """Resolve CNAME for *name*. Returns the canonical name or None."""
    try:
        answers = dns.resolver.resolve(name, "CNAME")
        return str(answers[0].target).rstrip(".")
    except dns.resolver.NXDOMAIN:
        return None
    except dns.resolver.NoAnswer:
        return None
    except dns.exception.DNSException as exc:
        logger.debug("DNS CNAME lookup failed for %s: %s", name, exc)
        return None


async def verify_dns_ownership(domain: DomainVerification) -> DnsVerificationResult:
    """Check that the user has added the required TXT record.

    Expected:  _haven-verify.{domain}  TXT  {verification_token}
    """
    txt_name = _txt_record_name(domain.domain)
    expected_value = domain.verification_token

    # Run blocking DNS call in thread pool
    txt_values = await asyncio.to_thread(_resolve_txt, txt_name)

    if expected_value in txt_values:
        return DnsVerificationResult(
            verified=True,
            message=f"TXT record verified for {domain.domain}",
        )

    return DnsVerificationResult(
        verified=False,
        message=(
            f"TXT record not found. Please add:\n"
            f"  Record type: TXT\n"
            f"  Name: {txt_name}\n"
            f"  Value: {expected_value}"
        ),
    )


async def verify_cname_pointing(
    domain: DomainVerification,
    tenant_slug: str,
    app_slug: str,
) -> DnsVerificationResult:
    """Check that the domain has a CNAME pointing to the app's sslip.io hostname."""
    expected_target = _app_hostname(tenant_slug, app_slug)
    cname = await asyncio.to_thread(_resolve_cname, domain.domain)

    if cname and cname == expected_target:
        return DnsVerificationResult(
            verified=True,
            message=f"CNAME verified: {domain.domain} → {expected_target}",
        )

    return DnsVerificationResult(
        verified=False,
        message=(
            f"CNAME record not found or incorrect. Please add:\n"
            f"  Record type: CNAME\n"
            f"  Name: {domain.domain}\n"
            f"  Value: {expected_target}"
        ),
    )


# ---------------------------------------------------------------------------
# cert-manager Certificate CRD
# ---------------------------------------------------------------------------


def _build_certificate_manifest(
    *,
    name: str,
    namespace: str,
    domain: str,
    secret_name: str,
    issuer_name: str,
) -> dict:
    return {
        "apiVersion": f"{_CERT_MANAGER_GROUP}/{_CERT_MANAGER_VERSION}",
        "kind": "Certificate",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {"haven/managed": "true"},
        },
        "spec": {
            "secretName": secret_name,
            "issuerRef": {
                "name": issuer_name,
                "kind": "ClusterIssuer",
            },
            "dnsNames": [domain],
        },
    }


def _build_wildcard_certificate_manifest(
    *,
    name: str,
    namespace: str,
    platform_domain: str,
    secret_name: str,
    issuer_name: str,
) -> dict:
    """Build a Certificate for *.apps.{platform_domain}."""
    return {
        "apiVersion": f"{_CERT_MANAGER_GROUP}/{_CERT_MANAGER_VERSION}",
        "kind": "Certificate",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {"haven/managed": "true"},
        },
        "spec": {
            "secretName": secret_name,
            "issuerRef": {
                "name": issuer_name,
                "kind": "ClusterIssuer",
            },
            "dnsNames": [
                f"*.apps.{platform_domain}",
                f"apps.{platform_domain}",
            ],
        },
    }


class CertManagerService:
    """Manages cert-manager Certificate CRD resources."""

    def __init__(self, k8s: K8sClient) -> None:
        self.k8s = k8s

    def _is_available(self) -> bool:
        return self.k8s.is_available() and self.k8s.custom_objects is not None

    async def issue_custom_domain_cert(
        self,
        *,
        domain: str,
        namespace: str,
    ) -> str:
        """Create a cert-manager Certificate for the custom domain.

        Returns the K8s Secret name that will hold the TLS cert.
        """
        if not self._is_available():
            logger.warning("K8s unavailable — skipping Certificate creation for %s", domain)
            return _cert_secret_name(domain)

        cert_name = _cert_secret_name(domain)
        secret_name = cert_name
        manifest = _build_certificate_manifest(
            name=cert_name,
            namespace=namespace,
            domain=domain,
            secret_name=secret_name,
            issuer_name=LETSENCRYPT_HTTP_ISSUER,
        )

        await self._create_or_replace_cert(namespace=namespace, name=cert_name, body=manifest)
        logger.info("Certificate issued for %s (secret: %s)", domain, secret_name)
        return secret_name

    async def issue_wildcard_cert(
        self,
        *,
        platform_domain: str,
        namespace: str = "haven-system",
    ) -> str:
        """Create a wildcard Certificate for *.apps.{platform_domain}.

        Requires DNS-01 ClusterIssuer (Cloudflare) to be configured in the cluster.
        Returns the K8s Secret name.
        """
        if not self._is_available():
            logger.warning("K8s unavailable — skipping wildcard Certificate")
            return "wildcard-apps-tls"

        safe = re.sub(r"[^a-z0-9-]", "-", platform_domain.lower())
        cert_name = f"wildcard-apps-{safe}"
        secret_name = f"wildcard-apps-tls-{safe}"

        manifest = _build_wildcard_certificate_manifest(
            name=cert_name,
            namespace=namespace,
            platform_domain=platform_domain,
            secret_name=secret_name,
            issuer_name=LETSENCRYPT_DNS_ISSUER,
        )

        await self._create_or_replace_cert(namespace=namespace, name=cert_name, body=manifest)
        logger.info("Wildcard Certificate issued for *.apps.%s (secret: %s)", platform_domain, secret_name)
        return secret_name

    async def get_cert_status(self, *, namespace: str, cert_name: str) -> CertificateStatus:
        """Read cert-manager Certificate status conditions."""
        if not self._is_available():
            return CertificateStatus.pending

        try:
            obj = await asyncio.to_thread(
                self.k8s.custom_objects.get_namespaced_custom_object,
                group=_CERT_MANAGER_GROUP,
                version=_CERT_MANAGER_VERSION,
                plural=_CERT_MANAGER_PLURAL_CERTS,
                namespace=namespace,
                name=cert_name,
            )
            conditions = obj.get("status", {}).get("conditions", [])
            for cond in conditions:
                if cond.get("type") == "Ready":
                    if cond.get("status") == "True":
                        return CertificateStatus.issued
                    elif cond.get("reason") in ("Failed", "NotFound"):
                        return CertificateStatus.failed
            return CertificateStatus.issuing
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to read Certificate status for %s: %s", cert_name, exc)
            return CertificateStatus.pending

    async def delete_cert(self, *, namespace: str, domain: str) -> None:
        """Delete the cert-manager Certificate for the given domain."""
        if not self._is_available():
            return
        cert_name = _cert_secret_name(domain)
        try:
            await asyncio.to_thread(
                self.k8s.custom_objects.delete_namespaced_custom_object,
                group=_CERT_MANAGER_GROUP,
                version=_CERT_MANAGER_VERSION,
                plural=_CERT_MANAGER_PLURAL_CERTS,
                namespace=namespace,
                name=cert_name,
            )
            logger.info("Deleted Certificate for %s", domain)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Certificate delete skipped for %s: %s", domain, exc)

    async def _create_or_replace_cert(
        self,
        *,
        namespace: str,
        name: str,
        body: dict,
    ) -> None:
        from kubernetes.client.exceptions import ApiException

        try:
            await asyncio.to_thread(
                self.k8s.custom_objects.get_namespaced_custom_object,
                group=_CERT_MANAGER_GROUP,
                version=_CERT_MANAGER_VERSION,
                plural=_CERT_MANAGER_PLURAL_CERTS,
                namespace=namespace,
                name=name,
            )
            # Already exists — patch it
            await asyncio.to_thread(
                self.k8s.custom_objects.patch_namespaced_custom_object,
                group=_CERT_MANAGER_GROUP,
                version=_CERT_MANAGER_VERSION,
                plural=_CERT_MANAGER_PLURAL_CERTS,
                namespace=namespace,
                name=name,
                body=body,
            )
        except ApiException as e:
            if e.status == 404:
                await asyncio.to_thread(
                    self.k8s.custom_objects.create_namespaced_custom_object,
                    group=_CERT_MANAGER_GROUP,
                    version=_CERT_MANAGER_VERSION,
                    plural=_CERT_MANAGER_PLURAL_CERTS,
                    namespace=namespace,
                    body=body,
                )
            else:
                raise


# ---------------------------------------------------------------------------
# HTTPRoute update helper
# ---------------------------------------------------------------------------


async def add_custom_domain_to_httproute(
    *,
    k8s: K8sClient,
    namespace: str,
    app_slug: str,
    custom_domain: str,
    tenant_slug: str,
    tls_secret_name: str | None = None,
) -> None:
    """Patch the app's HTTPRoute to include the custom domain hostname.

    Also adds TLS termination ref if a cert secret name is provided.
    """
    if not k8s.is_available() or k8s.custom_objects is None:
        logger.warning("K8s unavailable — skipping HTTPRoute update for %s", app_slug)
        return

    from kubernetes.client.exceptions import ApiException

    default_hostname = _app_hostname(tenant_slug, app_slug)

    try:
        existing = await asyncio.to_thread(
            k8s.custom_objects.get_namespaced_custom_object,
            group="gateway.networking.k8s.io",
            version="v1",
            plural="httproutes",
            namespace=namespace,
            name=app_slug,
        )
    except ApiException as e:
        if e.status == 404:
            logger.warning("HTTPRoute %s not found — cannot add custom domain", app_slug)
            return
        raise

    spec = existing.get("spec", {})
    hostnames: list[str] = spec.get("hostnames", [default_hostname])

    if custom_domain not in hostnames:
        hostnames.append(custom_domain)

    spec["hostnames"] = hostnames

    # Add TLS if secret provided
    if tls_secret_name and "tls" not in spec:
        spec["tls"] = {
            "mode": "Terminate",
            "certificateRefs": [{"name": tls_secret_name, "kind": "Secret"}],
        }

    existing["spec"] = spec

    try:
        await asyncio.to_thread(
            k8s.custom_objects.patch_namespaced_custom_object,
            group="gateway.networking.k8s.io",
            version="v1",
            plural="httproutes",
            namespace=namespace,
            name=app_slug,
            body=existing,
        )
        logger.info("HTTPRoute %s updated with custom domain %s", app_slug, custom_domain)
    except ApiException as e:
        logger.warning("HTTPRoute update skipped (CRD not available): %s", e.reason)


async def remove_custom_domain_from_httproute(
    *,
    k8s: K8sClient,
    namespace: str,
    app_slug: str,
    custom_domain: str,
) -> None:
    """Remove the custom domain hostname from the app's HTTPRoute."""
    if not k8s.is_available() or k8s.custom_objects is None:
        return

    from kubernetes.client.exceptions import ApiException

    try:
        existing = await asyncio.to_thread(
            k8s.custom_objects.get_namespaced_custom_object,
            group="gateway.networking.k8s.io",
            version="v1",
            plural="httproutes",
            namespace=namespace,
            name=app_slug,
        )
    except ApiException as e:
        if e.status == 404:
            return
        raise

    spec = existing.get("spec", {})
    hostnames: list[str] = spec.get("hostnames", [])
    spec["hostnames"] = [h for h in hostnames if h != custom_domain]
    existing["spec"] = spec

    try:
        await asyncio.to_thread(
            k8s.custom_objects.patch_namespaced_custom_object,
            group="gateway.networking.k8s.io",
            version="v1",
            plural="httproutes",
            namespace=namespace,
            name=app_slug,
            body=existing,
        )
        logger.info("Removed custom domain %s from HTTPRoute %s", custom_domain, app_slug)
    except ApiException as e:
        logger.warning("HTTPRoute update failed: %s", e.reason)


# ---------------------------------------------------------------------------
# Sync cert status helper (called periodically or on demand)
# ---------------------------------------------------------------------------


async def sync_certificate_status(
    *,
    domain_record: DomainVerification,
    app_namespace: str,
    k8s: K8sClient,
) -> CertificateStatus:
    """Query cert-manager for current Certificate status and return it."""
    svc = CertManagerService(k8s)
    cert_name = _cert_secret_name(domain_record.domain)
    return await svc.get_cert_status(namespace=app_namespace, cert_name=cert_name)


# ---------------------------------------------------------------------------
# LB hostname helper (exported for UI)
# ---------------------------------------------------------------------------


def get_lb_hostname() -> str:
    """Return the platform's LB hostname used for CNAME instructions."""
    return f"{settings.lb_ip}.sslip.io"
