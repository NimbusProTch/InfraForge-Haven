"""ET4: POST /tenants requires the platform-admin realm role.

The enterprise-only pivot (peki-idmi-unu-bi-joyful-newt.md) means
prospective customers don't self-serve tenant creation. The endpoint
is now behind the `platform-admin` realm role; everyone else gets a
403 with the "platform-admin role required" detail.
"""

import pytest

from app.auth.jwt import verify_token_not_revoked
from app.main import app


@pytest.mark.asyncio
async def test_create_tenant_without_admin_role_returns_403(async_client):
    """Authenticated user WITHOUT `platform-admin` role cannot POST /tenants."""

    # The default async_client grants platform-admin. Strip it for this test.
    app.dependency_overrides[verify_token_not_revoked] = lambda: {
        "sub": "normal-user",
        "email": "user@example.com",
        "realm_access": {"roles": ["default-roles-haven"]},
    }
    try:
        resp = await async_client.post(
            "/api/v1/tenants",
            json={
                "slug": "unauthorized-gemeente",
                "name": "Unauthorized Gemeente",
                "tier": "shared",
                "cpu_limit": "4",
                "memory_limit": "8Gi",
                "storage_limit": "50Gi",
            },
        )
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)

    assert resp.status_code == 403
    assert "platform-admin" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_tenant_without_any_roles_returns_403(async_client):
    """Missing `realm_access` claim entirely is treated as non-admin."""
    app.dependency_overrides[verify_token_not_revoked] = lambda: {
        "sub": "no-roles",
        "email": "no@example.com",
    }
    try:
        resp = await async_client.post(
            "/api/v1/tenants",
            json={
                "slug": "no-roles-gemeente",
                "name": "No Roles Gemeente",
                "tier": "shared",
                "cpu_limit": "4",
                "memory_limit": "8Gi",
                "storage_limit": "50Gi",
            },
        )
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_tenant_with_admin_role_succeeds(async_client):
    """Default fixture has platform-admin → creation succeeds (201)."""
    resp = await async_client.post(
        "/api/v1/tenants",
        json={
            "slug": "admin-gemeente",
            "name": "Admin Gemeente",
            "tier": "shared",
            "cpu_limit": "4",
            "memory_limit": "8Gi",
            "storage_limit": "50Gi",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["slug"] == "admin-gemeente"


@pytest.mark.asyncio
async def test_create_tenant_ignores_client_scoped_platform_admin(async_client):
    """Only realm-level `platform-admin` counts, not a client role."""
    app.dependency_overrides[verify_token_not_revoked] = lambda: {
        "sub": "client-admin",
        "email": "client@example.com",
        "realm_access": {"roles": ["default-roles-haven"]},
        # Client-scoped role must NOT bypass the realm-level check.
        "resource_access": {"iyziops-api": {"roles": ["platform-admin"]}},
    }
    try:
        resp = await async_client.post(
            "/api/v1/tenants",
            json={
                "slug": "client-scoped",
                "name": "Client Scoped",
                "tier": "shared",
                "cpu_limit": "4",
                "memory_limit": "8Gi",
                "storage_limit": "50Gi",
            },
        )
    finally:
        app.dependency_overrides.pop(verify_token_not_revoked, None)

    assert resp.status_code == 403
