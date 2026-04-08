"""Tests for audit log endpoints and audit service."""

import uuid

import pytest

from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.services import audit_service

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def audit_tenant(db_session):
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="audit-tenant",
        name="Audit Tenant",
        namespace="tenant-audit-tenant",
        keycloak_realm="audit-tenant",
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_creates_log_entry(db_session, audit_tenant):
    """audit() creates an AuditLog row with the expected fields."""
    entry = await audit_service.audit(
        db_session,
        tenant_id=audit_tenant.id,
        action=audit_service.APP_CREATE,
        user_id="user-123",
        resource_type="app",
        resource_id="my-app",
        extra={"name": "My App"},
        ip_address="1.2.3.4",
    )
    await db_session.commit()

    assert entry.id is not None
    assert entry.tenant_id == audit_tenant.id
    assert entry.action == "app.create"
    assert entry.user_id == "user-123"
    assert entry.resource_type == "app"
    assert entry.resource_id == "my-app"
    assert entry.extra == {"name": "My App"}
    assert entry.ip_address == "1.2.3.4"
    assert entry.created_at is not None


@pytest.mark.asyncio
async def test_audit_optional_fields_default_none(db_session, audit_tenant):
    """Optional fields default to None without error."""
    entry = await audit_service.audit(
        db_session,
        tenant_id=audit_tenant.id,
        action=audit_service.TENANT_DELETE,
    )
    await db_session.commit()

    assert entry.user_id is None
    assert entry.resource_type is None
    assert entry.resource_id is None
    assert entry.extra is None
    assert entry.ip_address is None


@pytest.mark.asyncio
async def test_audit_multiple_actions_same_tenant(db_session, audit_tenant):
    """Multiple audit entries can be written for the same tenant."""
    for action in [audit_service.APP_CREATE, audit_service.DEPLOY_TRIGGER, audit_service.APP_DELETE]:
        await audit_service.audit(db_session, tenant_id=audit_tenant.id, action=action)
    await db_session.commit()

    from sqlalchemy import select

    result = await db_session.execute(select(AuditLog).where(AuditLog.tenant_id == audit_tenant.id))
    logs = result.scalars().all()
    assert len(logs) == 3
    actions = {log.action for log in logs}
    assert actions == {audit_service.APP_CREATE, audit_service.DEPLOY_TRIGGER, audit_service.APP_DELETE}


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_logs_empty_for_new_tenant(async_client, sample_tenant):
    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/audit-logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_audit_logs_tenant_not_found(async_client):
    resp = await async_client.get("/api/v1/tenants/does-not-exist/audit-logs")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_audit_logs_filter_by_action(async_client, db_session, sample_tenant):
    """Filtering by action returns only matching entries."""
    for action in [audit_service.APP_CREATE, audit_service.APP_CREATE, audit_service.TENANT_UPDATE]:
        await audit_service.audit(db_session, tenant_id=sample_tenant.id, action=action)
    await db_session.commit()

    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/audit-logs?action=app.create")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(item["action"] == "app.create" for item in data["items"])


@pytest.mark.asyncio
async def test_audit_logs_filter_by_user_id(async_client, db_session, sample_tenant):
    await audit_service.audit(db_session, tenant_id=sample_tenant.id, action="app.create", user_id="alice")
    await audit_service.audit(db_session, tenant_id=sample_tenant.id, action="app.delete", user_id="bob")
    await db_session.commit()

    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/audit-logs?user_id=alice")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["user_id"] == "alice"


@pytest.mark.asyncio
async def test_audit_logs_pagination(async_client, db_session, sample_tenant):
    """Pagination returns correct slice."""
    for i in range(15):
        await audit_service.audit(db_session, tenant_id=sample_tenant.id, action="app.update", resource_id=f"app-{i}")
    await db_session.commit()

    # First page of 10
    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/audit-logs?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 15
    assert len(data["items"]) == 10
    assert data["page"] == 1

    # Second page (remaining 5)
    resp2 = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/audit-logs?page=2&page_size=10")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2["items"]) == 5


@pytest.mark.asyncio
async def test_audit_logs_filter_by_resource_type(async_client, db_session, sample_tenant):
    await audit_service.audit(db_session, tenant_id=sample_tenant.id, action="app.create", resource_type="app")
    await audit_service.audit(db_session, tenant_id=sample_tenant.id, action="service.create", resource_type="service")
    await db_session.commit()

    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/audit-logs?resource_type=service")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["resource_type"] == "service"


# ---------------------------------------------------------------------------
# H0-1: Cross-tenant isolation regression tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_logs_cross_tenant_access_denied(async_client, db_session, sample_tenant):
    """A non-member must NOT be able to read another tenant's audit logs.

    Regression test for the H0-1 hot-fix: prior to the fix, audit.py looked
    up the tenant by slug but never verified the caller was a member of it,
    so any authenticated user could read any tenant's audit logs.
    """
    # Create a second tenant where 'test-user' is NOT a member
    other_tenant = Tenant(
        id=uuid.uuid4(),
        slug="other-gemeente",
        name="Other Gemeente",
        namespace="tenant-other-gemeente",
        keycloak_realm="other-gemeente",
    )
    db_session.add(other_tenant)
    await db_session.commit()

    # Write some audit data into the other tenant
    await audit_service.audit(db_session, tenant_id=other_tenant.id, action="app.create", resource_id="secret-app")
    await db_session.commit()

    # 'test-user' (default async_client) is not a member of 'other-gemeente'
    resp = await async_client.get(f"/api/v1/tenants/{other_tenant.slug}/audit-logs")
    assert resp.status_code == 403
    assert "not a member" in resp.json()["detail"].lower()
