"""L05 — tests for ArgoCDService.get_live_status.

The /tenants/{slug}/apps/{app}/live-status endpoint is polled by the UI
every ~10 s to render a Healthy/Degraded/Progressing pill on the app
detail header. The helper must:

- always return the documented shape (so the UI never has to handle
  partial responses)
- return `available=False` when ArgoCD is unreachable or misconfigured
  (UI hides the badge in that case)
- extract a one-line `reason` from operationState.message, falling back
  to the last conditions[].message — so a Degraded app carries enough
  context for a tooltip instead of just a red dot.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.argocd_service import ArgoCDService


def _svc(url: str = "http://argocd.test", token: str = "tok") -> ArgoCDService:
    s = ArgoCDService.__new__(ArgoCDService)
    s._url = url
    s._token = token
    return s


def _mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.is_success = status_code < 400
    r.json = MagicMock(return_value=json_data or {})
    return r


EXPECTED_KEYS = {"health", "sync", "reason", "phase", "finished_at", "available"}


class TestGetLiveStatusShape:
    @pytest.mark.asyncio
    async def test_url_unset_returns_unavailable_with_full_shape(self):
        svc = ArgoCDService.__new__(ArgoCDService)
        svc._url = ""
        svc._token = ""
        result = await svc.get_live_status("any-app")
        assert set(result.keys()) == EXPECTED_KEYS
        assert result["available"] is False
        assert result["health"] == "Unknown"

    @pytest.mark.asyncio
    async def test_404_marks_app_missing_but_argocd_available(self):
        svc = _svc()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(404))
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await svc.get_live_status("missing-app")
        assert result["available"] is True
        assert result["health"] == "Missing"
        assert "not present" in result["reason"].lower() or "missing" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_5xx_marks_argocd_unavailable(self):
        svc = _svc()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(503))
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await svc.get_live_status("any-app")
        assert result["available"] is False
        assert "503" in result["reason"]

    @pytest.mark.asyncio
    async def test_network_exception_marks_unavailable(self):
        svc = _svc()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.side_effect = OSError("DNS fail")
            result = await svc.get_live_status("any-app")
        assert set(result.keys()) == EXPECTED_KEYS
        assert result["available"] is False


class TestGetLiveStatusReasonExtraction:
    @pytest.mark.asyncio
    async def test_healthy_synced_app_carries_no_reason(self):
        svc = _svc()
        body = {
            "status": {
                "health": {"status": "Healthy"},
                "sync": {"status": "Synced"},
                "operationState": {
                    "phase": "Succeeded",
                    "message": "successfully synced",
                    "finishedAt": "2026-04-19T01:00:00Z",
                },
            }
        }
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(200, body))
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await svc.get_live_status("happy-app")
        assert result["health"] == "Healthy"
        assert result["sync"] == "Synced"
        assert result["reason"] == "successfully synced"
        assert result["phase"] == "Succeeded"
        assert result["finished_at"] == "2026-04-19T01:00:00Z"

    @pytest.mark.asyncio
    async def test_degraded_app_falls_back_to_conditions(self):
        """When operationState.message is empty, the helper must look at
        status.conditions[-1].message to surface the reason."""
        svc = _svc()
        body = {
            "status": {
                "health": {"status": "Degraded"},
                "sync": {"status": "Synced"},
                "operationState": {"phase": "Failed", "message": ""},
                "conditions": [
                    {"type": "ComparisonError", "message": "old benign info"},
                    {"type": "SyncError", "message": "ImagePullBackOff for haven-api: pull access denied"},
                ],
            }
        }
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(200, body))
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await svc.get_live_status("sad-app")
        assert result["health"] == "Degraded"
        assert "ImagePullBackOff" in result["reason"]
        assert "pull access denied" in result["reason"]

    @pytest.mark.asyncio
    async def test_degraded_with_no_conditions_returns_empty_reason(self):
        svc = _svc()
        body = {
            "status": {
                "health": {"status": "Degraded"},
                "sync": {"status": "OutOfSync"},
                "operationState": {},
                "conditions": [],
            }
        }
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(200, body))
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await svc.get_live_status("orphan-app")
        assert result["health"] == "Degraded"
        assert result["reason"] == ""
        # Available is still True — ArgoCD answered, the app just has no message.
        assert result["available"] is True

    @pytest.mark.asyncio
    async def test_degraded_skips_empty_conditions_picks_latest_with_message(self):
        svc = _svc()
        body = {
            "status": {
                "health": {"status": "Degraded"},
                "sync": {"status": "Synced"},
                "operationState": {},
                "conditions": [
                    {"type": "X", "message": "real reason here"},
                    {"type": "Y", "message": ""},
                    {"type": "Z", "message": ""},
                ],
            }
        }
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(200, body))
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await svc.get_live_status("app")
        assert result["reason"] == "real reason here"
