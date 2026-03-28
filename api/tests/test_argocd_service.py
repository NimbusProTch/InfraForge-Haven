"""Tests for Sprint I-6: ArgoCD Sync API + Deployment History.

Covers:
  - ArgoCDService.get_app_status
  - ArgoCDService.wait_for_healthy
  - ArgoCDService.trigger_sync
  - ArgoCDService.get_app_history   (new)
  - ArgoCDService.rollback_app       (new)
  - GET  /tenants/{slug}/apps/{app}/sync-status
  - POST /tenants/{slug}/apps/{app}/sync
  - GET  /tenants/{slug}/apps/{app}/deploy-history
  - POST /tenants/{slug}/apps/{app}/rollback/{revision}
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.argocd_service import ArgoCDService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(url: str = "http://argocd.test", token: str = "tok") -> ArgoCDService:
    """Create ArgoCDService bypassing __init__ to avoid settings fallback."""
    svc = ArgoCDService.__new__(ArgoCDService)
    svc._url = url
    svc._token = token
    return svc


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = status_code < 400
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# get_app_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_app_status_healthy():
    svc = _make_service()
    resp_data = {
        "status": {
            "health": {"status": "Healthy"},
            "sync": {"status": "Synced"},
            "operationState": {},
        }
    }
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(200, resp_data))

        result = await svc.get_app_status("gemeente-a-my-app")

    assert result["health"] == "Healthy"
    assert result["sync"] == "Synced"


@pytest.mark.asyncio
async def test_get_app_status_not_found():
    svc = _make_service()
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(404))

        result = await svc.get_app_status("nonexistent-app")

    assert result["health"] == "Missing"
    assert result["sync"] == "Unknown"


@pytest.mark.asyncio
async def test_get_app_status_api_error():
    svc = _make_service()
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(500))

        result = await svc.get_app_status("bad-app")

    assert result == {}


@pytest.mark.asyncio
async def test_get_app_status_no_url():
    svc = _make_service(url="")
    result = await svc.get_app_status("my-app")
    assert result == {}


# ---------------------------------------------------------------------------
# wait_for_healthy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_healthy_success():
    svc = _make_service()
    with (
        patch.object(svc, "get_app_status", new=AsyncMock(return_value={"health": "Healthy", "sync": "Synced"})),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        ok, msg = await svc.wait_for_healthy("my-app", timeout=10)

    assert ok is True
    assert "Healthy" in msg


@pytest.mark.asyncio
async def test_wait_for_healthy_timeout():
    svc = _make_service()
    with (
        patch.object(svc, "get_app_status", new=AsyncMock(return_value={"health": "Progressing", "sync": "Syncing"})),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        ok, msg = await svc.wait_for_healthy("my-app", timeout=10)

    assert ok is False
    assert "not healthy" in msg


@pytest.mark.asyncio
async def test_wait_for_healthy_degraded():
    svc = _make_service()
    degraded = {"health": "Degraded", "sync": "OutOfSync", "operationState": {"message": "CrashLoopBackOff"}}
    with (
        patch.object(svc, "get_app_status", new=AsyncMock(return_value=degraded)),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        ok, msg = await svc.wait_for_healthy("my-app", timeout=30)

    assert ok is False
    assert "CrashLoopBackOff" in msg


@pytest.mark.asyncio
async def test_wait_for_healthy_no_url():
    svc = _make_service(url="")
    ok, msg = await svc.wait_for_healthy("my-app")
    assert ok is True
    assert "skipped" in msg.lower() or "not configured" in msg.lower()


# ---------------------------------------------------------------------------
# trigger_sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_sync_success():
    svc = _make_service()
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_response(200, {}))

        result = await svc.trigger_sync("gemeente-a-my-app")

    assert result is True


@pytest.mark.asyncio
async def test_trigger_sync_failure():
    svc = _make_service()
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_response(503))

        result = await svc.trigger_sync("gemeente-a-my-app")

    assert result is False


# ---------------------------------------------------------------------------
# get_app_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_app_history_returns_list():
    svc = _make_service()
    history = [
        {"id": 1, "revision": "abc123", "deployedAt": "2025-01-01T00:00:00Z"},
        {"id": 2, "revision": "def456", "deployedAt": "2025-01-02T00:00:00Z"},
    ]
    resp_data = {"status": {"history": history}}

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(200, resp_data))

        result = await svc.get_app_history("gemeente-a-my-app")

    assert len(result) == 2
    assert result[0]["revision"] == "abc123"
    assert result[1]["id"] == 2


@pytest.mark.asyncio
async def test_get_app_history_no_url():
    svc = _make_service(url="")
    result = await svc.get_app_history("my-app")
    assert result == []


@pytest.mark.asyncio
async def test_get_app_history_api_failure():
    svc = _make_service()
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(500))

        result = await svc.get_app_history("my-app")

    assert result == []


@pytest.mark.asyncio
async def test_get_app_history_empty_when_no_history_key():
    svc = _make_service()
    resp_data = {"status": {}}  # no history key

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(200, resp_data))

        result = await svc.get_app_history("my-app")

    assert result == []


# ---------------------------------------------------------------------------
# rollback_app
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_app_success():
    svc = _make_service()
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_response(200, {}))

        result = await svc.rollback_app("gemeente-a-my-app", 3)

    assert result is True


@pytest.mark.asyncio
async def test_rollback_app_failure():
    svc = _make_service()
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_response(400, {"message": "invalid revision"}))

        result = await svc.rollback_app("gemeente-a-my-app", 99)

    assert result is False


@pytest.mark.asyncio
async def test_rollback_app_no_url():
    svc = _make_service(url="")
    result = await svc.rollback_app("my-app", 1)
    assert result is False


# ---------------------------------------------------------------------------
# API endpoint tests (via async_client)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_endpoint_triggers_argocd(async_client, sample_tenant, db_session):
    """POST /sync should call trigger_sync and return triggered=True."""
    from app.deps import get_argocd
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="sync-app",
        name="Sync App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    mock_argocd = MagicMock()
    mock_argocd.trigger_sync = AsyncMock(return_value=True)
    fastapi_app.dependency_overrides[get_argocd] = lambda: mock_argocd

    try:
        resp = await async_client.post(
            f"/api/v1/tenants/{sample_tenant.slug}/apps/sync-app/sync"
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["triggered"] is True
        assert "sync-app" in body["app_name"]
        mock_argocd.trigger_sync.assert_awaited_once()
    finally:
        fastapi_app.dependency_overrides.pop(get_argocd, None)


@pytest.mark.asyncio
async def test_sync_status_endpoint(async_client, sample_tenant, db_session):
    """GET /sync-status should return ArgoCD health/sync status."""
    from app.deps import get_argocd
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="status-app",
        name="Status App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    mock_argocd = MagicMock()
    mock_argocd.get_app_status = AsyncMock(return_value={"health": "Healthy", "sync": "Synced"})
    fastapi_app.dependency_overrides[get_argocd] = lambda: mock_argocd

    try:
        resp = await async_client.get(
            f"/api/v1/tenants/{sample_tenant.slug}/apps/status-app/sync-status"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["health"] == "Healthy"
        assert body["sync"] == "Synced"
    finally:
        fastapi_app.dependency_overrides.pop(get_argocd, None)


@pytest.mark.asyncio
async def test_deploy_history_endpoint(async_client, sample_tenant, db_session):
    """GET /deploy-history should return list of ArgoCD revisions."""
    from app.deps import get_argocd
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="history-app",
        name="History App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    history = [{"id": 1, "revision": "abc"}, {"id": 2, "revision": "def"}]
    mock_argocd = MagicMock()
    mock_argocd.get_app_history = AsyncMock(return_value=history)
    fastapi_app.dependency_overrides[get_argocd] = lambda: mock_argocd

    try:
        resp = await async_client.get(
            f"/api/v1/tenants/{sample_tenant.slug}/apps/history-app/deploy-history"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["revision"] == "abc"
    finally:
        fastapi_app.dependency_overrides.pop(get_argocd, None)


@pytest.mark.asyncio
async def test_argocd_rollback_endpoint_success(async_client, sample_tenant, db_session):
    """POST /rollback/{revision} should trigger ArgoCD rollback."""
    from app.deps import get_argocd
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="rollback-app",
        name="Rollback App",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    mock_argocd = MagicMock()
    mock_argocd.rollback_app = AsyncMock(return_value=True)
    fastapi_app.dependency_overrides[get_argocd] = lambda: mock_argocd

    try:
        resp = await async_client.post(
            f"/api/v1/tenants/{sample_tenant.slug}/apps/rollback-app/rollback/3"
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["triggered"] is True
        assert body["revision"] == 3
        mock_argocd.rollback_app.assert_awaited_once_with(f"{sample_tenant.slug}-rollback-app", 3)
    finally:
        fastapi_app.dependency_overrides.pop(get_argocd, None)


@pytest.mark.asyncio
async def test_argocd_rollback_endpoint_fails_when_argocd_returns_false(async_client, sample_tenant, db_session):
    """POST /rollback returns 502 when ArgoCD rollback fails."""
    from app.deps import get_argocd
    from app.main import app as fastapi_app
    from app.models.application import Application as AppModel

    app_obj = AppModel(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        slug="rollback-fail",
        name="Rollback Fail",
        repo_url="https://github.com/org/repo",
        branch="main",
    )
    db_session.add(app_obj)
    await db_session.commit()

    mock_argocd = MagicMock()
    mock_argocd.rollback_app = AsyncMock(return_value=False)
    fastapi_app.dependency_overrides[get_argocd] = lambda: mock_argocd

    try:
        resp = await async_client.post(
            f"/api/v1/tenants/{sample_tenant.slug}/apps/rollback-fail/rollback/99"
        )
        assert resp.status_code == 502
    finally:
        fastapi_app.dependency_overrides.pop(get_argocd, None)
