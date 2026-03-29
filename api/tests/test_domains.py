"""Tests for custom domain management (Sprint 6).

Covers:
- Domain CRUD (add, list, get, delete)
- Duplicate domain rejection
- Tenant / app 404 handling
- DNS verification flow (mocked DNS)
- cert-manager Certificate creation (mocked K8s)
- HTTPRoute update (mocked K8s)
- Wildcard cert endpoint
- Domain schema validation
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.domain import CertificateStatus
from app.schemas.domain import DomainCreate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_tenant(async_client, slug="t1"):
    resp = await async_client.post(
        "/api/v1/tenants",
        json={
            "slug": slug,
            "name": f"Tenant {slug}",
            "namespace": f"tenant-{slug}",
            "keycloak_realm": slug,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_app(async_client, tenant_slug, app_slug="myapp"):
    resp = await async_client.post(
        f"/api/v1/tenants/{tenant_slug}/apps",
        json={
            "slug": app_slug,
            "name": "My App",
            "repo_url": "https://github.com/org/repo",
            "branch": "main",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Test 1: Add domain — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_domain_success(async_client):
    await _create_tenant(async_client, "add-domain")
    await _create_app(async_client, "add-domain", "app1")

    resp = await async_client.post(
        "/api/v1/tenants/add-domain/apps/app1/domains",
        json={"domain": "myapp.example.com"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["domain"] == "myapp.example.com"
    assert data["certificate_status"] == "pending"
    assert data["verified_at"] is None
    assert "verification_token" in data
    assert data["txt_record_name"] == "_haven-verify.myapp.example.com"
    assert data["txt_record_value"] == data["verification_token"]


# ---------------------------------------------------------------------------
# Test 2: Add domain — strips protocol prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_domain_rejects_protocol_prefix(async_client):
    await _create_tenant(async_client, "proto-tenant")
    await _create_app(async_client, "proto-tenant", "app2")

    resp = await async_client.post(
        "/api/v1/tenants/proto-tenant/apps/app2/domains",
        json={"domain": "https://myapp.example.com"},
    )
    assert resp.status_code == 422  # Pydantic validation error


# ---------------------------------------------------------------------------
# Test 3: Add domain — invalid format (no dot)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_domain_rejects_invalid_format(async_client):
    await _create_tenant(async_client, "inv-tenant")
    await _create_app(async_client, "inv-tenant", "app3")

    resp = await async_client.post(
        "/api/v1/tenants/inv-tenant/apps/app3/domains",
        json={"domain": "notadomain"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test 4: Duplicate domain — 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_domain_duplicate_conflict(async_client):
    await _create_tenant(async_client, "dup-tenant")
    await _create_app(async_client, "dup-tenant", "app4")

    payload = {"domain": "dup.example.com"}
    r1 = await async_client.post("/api/v1/tenants/dup-tenant/apps/app4/domains", json=payload)
    assert r1.status_code == 201

    r2 = await async_client.post("/api/v1/tenants/dup-tenant/apps/app4/domains", json=payload)
    assert r2.status_code == 409


# ---------------------------------------------------------------------------
# Test 5: List domains — empty then populated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_domains(async_client):
    await _create_tenant(async_client, "list-tenant")
    await _create_app(async_client, "list-tenant", "app5")

    base = "/api/v1/tenants/list-tenant/apps/app5/domains"

    resp_empty = await async_client.get(base)
    assert resp_empty.status_code == 200
    assert resp_empty.json() == []

    await async_client.post(base, json={"domain": "one.example.com"})
    await async_client.post(base, json={"domain": "two.example.com"})

    resp_list = await async_client.get(base)
    assert resp_list.status_code == 200
    domains = resp_list.json()
    assert len(domains) == 2
    domain_names = {d["domain"] for d in domains}
    assert {"one.example.com", "two.example.com"} == domain_names


# ---------------------------------------------------------------------------
# Test 6: Get domain — success and 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_domain_found_and_not_found(async_client):
    await _create_tenant(async_client, "get-tenant")
    await _create_app(async_client, "get-tenant", "app6")

    base = "/api/v1/tenants/get-tenant/apps/app6/domains"
    await async_client.post(base, json={"domain": "get.example.com"})

    resp_found = await async_client.get(f"{base}/get.example.com")
    assert resp_found.status_code == 200
    assert resp_found.json()["domain"] == "get.example.com"

    resp_404 = await async_client.get(f"{base}/missing.example.com")
    assert resp_404.status_code == 404


# ---------------------------------------------------------------------------
# Test 7: Delete domain — success and 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_domain(async_client):
    await _create_tenant(async_client, "del-tenant")
    await _create_app(async_client, "del-tenant", "app7")

    base = "/api/v1/tenants/del-tenant/apps/app7/domains"
    await async_client.post(base, json={"domain": "del.example.com"})

    resp_del = await async_client.delete(f"{base}/del.example.com")
    assert resp_del.status_code == 204

    resp_get = await async_client.get(f"{base}/del.example.com")
    assert resp_get.status_code == 404

    # Second delete → 404
    resp_del2 = await async_client.delete(f"{base}/del.example.com")
    assert resp_del2.status_code == 404


# ---------------------------------------------------------------------------
# Test 8: Verify domain — DNS TXT check succeeds → certificate issuing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_domain_success(async_client):
    await _create_tenant(async_client, "verify-tenant")
    await _create_app(async_client, "verify-tenant", "app8")

    base = "/api/v1/tenants/verify-tenant/apps/app8/domains"
    add_resp = await async_client.post(base, json={"domain": "verify.example.com"})
    assert add_resp.status_code == 201
    token = add_resp.json()["verification_token"]

    # Mock DNS resolution: TXT record contains the verification token
    with (
        patch(
            "app.services.domain_service._resolve_txt",
            return_value=[token],
        ),
        patch(
            "app.services.domain_service.CertManagerService.issue_custom_domain_cert",
            new_callable=AsyncMock,
            return_value="custom-domain-tls-verify-example-com",
        ),
        patch(
            "app.services.domain_service.add_custom_domain_to_httproute",
            new_callable=AsyncMock,
        ),
    ):
        resp = await async_client.post(f"{base}/verify.example.com/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is True
        assert data["certificate_status"] == "issuing"


# ---------------------------------------------------------------------------
# Test 9: Verify domain — DNS TXT check fails
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_domain_txt_not_found(async_client):
    await _create_tenant(async_client, "norecord-tenant")
    await _create_app(async_client, "norecord-tenant", "app9")

    base = "/api/v1/tenants/norecord-tenant/apps/app9/domains"
    await async_client.post(base, json={"domain": "norecord.example.com"})

    with patch("app.services.domain_service._resolve_txt", return_value=[]):
        resp = await async_client.post(f"{base}/norecord.example.com/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        assert data["certificate_status"] == "pending"
        assert "TXT record not found" in data["message"]


# ---------------------------------------------------------------------------
# Test 10: Tenant not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_tenant_not_found(async_client):
    resp = await async_client.post(
        "/api/v1/tenants/ghost-tenant/apps/app/domains",
        json={"domain": "ghost.example.com"},
    )
    assert resp.status_code == 404
    assert "Tenant not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test 11: App not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_app_not_found(async_client):
    await _create_tenant(async_client, "appless-tenant")

    resp = await async_client.post(
        "/api/v1/tenants/appless-tenant/apps/ghost-app/domains",
        json={"domain": "ghost-app.example.com"},
    )
    assert resp.status_code == 404
    assert "Application not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test 12: Domain schema validator — lowercases and strips whitespace
# ---------------------------------------------------------------------------


def test_domain_schema_normalises():
    schema = DomainCreate(domain="  MyApp.Example.COM  ")
    assert schema.domain == "myapp.example.com"


# ---------------------------------------------------------------------------
# Test 13: Sync cert status endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_cert_status(async_client):
    await _create_tenant(async_client, "sync-tenant")
    await _create_app(async_client, "sync-tenant", "app13")

    base = "/api/v1/tenants/sync-tenant/apps/app13/domains"
    await async_client.post(base, json={"domain": "sync.example.com"})

    with patch(
        "app.services.domain_service.CertManagerService.get_cert_status",
        new_callable=AsyncMock,
        return_value=CertificateStatus.issued,
    ):
        resp = await async_client.post(f"{base}/sync.example.com/sync-cert")
        assert resp.status_code == 200
        assert resp.json()["certificate_status"] == "issued"


# ---------------------------------------------------------------------------
# Test 14: Wildcard cert endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wildcard_cert_endpoint(async_client):
    with patch(
        "app.services.domain_service.CertManagerService.issue_wildcard_cert",
        new_callable=AsyncMock,
        return_value="wildcard-apps-tls-example-com",
    ):
        resp = await async_client.post(
            "/api/v1/platform/domains/wildcard-cert",
            json={"platform_domain": "example.com"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["wildcard_domain"] == "*.apps.example.com"
        assert data["tls_secret_name"] == "wildcard-apps-tls-example-com"
