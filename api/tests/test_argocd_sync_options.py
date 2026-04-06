"""Tests for ArgoCD sync options and resource diff (Phase 5A).

Covers:
  - trigger_sync with prune/force/dry_run options
  - get_resource_diff returns OutOfSync resources
  - SyncOptions schema validation
  - Sync endpoint accepts options body
  - Sync-diff endpoint
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.argocd_service import ArgoCDService


# ---------------------------------------------------------------------------
# trigger_sync options tests
# ---------------------------------------------------------------------------


class TestTriggerSyncOptions:
    def test_signature_has_options(self):
        """trigger_sync should accept prune, force, dry_run params."""
        sig = inspect.signature(ArgoCDService.trigger_sync)
        assert "prune" in sig.parameters
        assert "force" in sig.parameters
        assert "dry_run" in sig.parameters

    def test_default_options(self):
        """Default: prune=True, force=False, dry_run=False."""
        sig = inspect.signature(ArgoCDService.trigger_sync)
        assert sig.parameters["prune"].default is True
        assert sig.parameters["force"].default is False
        assert sig.parameters["dry_run"].default is False

    @pytest.mark.asyncio
    async def test_sync_default_body(self):
        """Default sync should send {prune: true}."""
        svc = ArgoCDService(argocd_url="http://argocd:8080", auth_token="test")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await svc.trigger_sync("test-app")

            assert result is True
            call_kwargs = mock_client.post.call_args
            json_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert json_body["prune"] is True
            assert "strategy" not in json_body
            assert "dryRun" not in json_body

    @pytest.mark.asyncio
    async def test_sync_force_option(self):
        """force=True should add strategy.apply.force."""
        svc = ArgoCDService(argocd_url="http://argocd:8080", auth_token="test")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            await svc.trigger_sync("test-app", force=True)

            json_body = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
            assert json_body["strategy"] == {"apply": {"force": True}}

    @pytest.mark.asyncio
    async def test_sync_dry_run_option(self):
        """dry_run=True should add dryRun flag."""
        svc = ArgoCDService(argocd_url="http://argocd:8080", auth_token="test")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            await svc.trigger_sync("test-app", dry_run=True)

            json_body = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
            assert json_body["dryRun"] is True

    @pytest.mark.asyncio
    async def test_sync_no_prune(self):
        """prune=False should be passed through."""
        svc = ArgoCDService(argocd_url="http://argocd:8080", auth_token="test")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            await svc.trigger_sync("test-app", prune=False)

            json_body = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
            assert json_body["prune"] is False

    @pytest.mark.asyncio
    async def test_sync_returns_false_when_unconfigured(self):
        """Sync should return False when URL not set."""
        svc = ArgoCDService(argocd_url="", auth_token="")
        result = await svc.trigger_sync("test-app")
        assert result is False


# ---------------------------------------------------------------------------
# get_resource_diff tests
# ---------------------------------------------------------------------------


class TestGetResourceDiff:
    def test_method_exists(self):
        """get_resource_diff should exist on ArgoCDService."""
        assert hasattr(ArgoCDService, "get_resource_diff")

    @pytest.mark.asyncio
    async def test_diff_returns_empty_when_unconfigured(self):
        """Should return empty list when URL not set."""
        svc = ArgoCDService(argocd_url="", auth_token="")
        result = await svc.get_resource_diff("test-app")
        assert result == []

    @pytest.mark.asyncio
    async def test_diff_filters_out_of_sync_resources(self):
        """Should return only OutOfSync or unhealthy resources."""
        svc = ArgoCDService(argocd_url="http://argocd:8080", auth_token="test")

        mock_data = {
            "status": {
                "resources": [
                    {"kind": "Deployment", "name": "myapp", "status": "OutOfSync", "health": {"status": "Healthy"}},
                    {"kind": "Service", "name": "myapp", "status": "Synced", "health": {"status": "Healthy"}},
                    {"kind": "HPA", "name": "myapp", "status": "Synced", "health": {"status": "Degraded", "message": "invalid metrics"}},
                ],
            }
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_response.json.return_value = mock_data
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            diffs = await svc.get_resource_diff("test-app")

        # Should have 2: Deployment (OutOfSync) + HPA (Degraded)
        assert len(diffs) == 2
        assert diffs[0]["kind"] == "Deployment"
        assert diffs[0]["sync_status"] == "OutOfSync"
        assert diffs[1]["kind"] == "HPA"
        assert diffs[1]["health_status"] == "Degraded"
        assert diffs[1]["health_message"] == "invalid metrics"

    @pytest.mark.asyncio
    async def test_diff_all_synced(self):
        """When all resources are synced and healthy, return empty."""
        svc = ArgoCDService(argocd_url="http://argocd:8080", auth_token="test")

        mock_data = {
            "status": {
                "resources": [
                    {"kind": "Deployment", "name": "myapp", "status": "Synced", "health": {"status": "Healthy"}},
                    {"kind": "Service", "name": "myapp", "status": "Synced", "health": {"status": "Healthy"}},
                ],
            }
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_response.json.return_value = mock_data
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            diffs = await svc.get_resource_diff("test-app")

        assert diffs == []


# ---------------------------------------------------------------------------
# SyncOptions schema tests
# ---------------------------------------------------------------------------


class TestSyncOptionsSchema:
    def test_default_values(self):
        from app.routers.deployments import SyncOptions

        opts = SyncOptions()
        assert opts.prune is True
        assert opts.force is False
        assert opts.dry_run is False

    def test_custom_values(self):
        from app.routers.deployments import SyncOptions

        opts = SyncOptions(prune=False, force=True, dry_run=True)
        assert opts.prune is False
        assert opts.force is True
        assert opts.dry_run is True


# ---------------------------------------------------------------------------
# Connected apps enrichment tests
# ---------------------------------------------------------------------------


class TestConnectedAppsEnrichment:
    def test_service_response_has_connected_apps_field(self):
        """ManagedServiceResponse should include connected_apps."""
        from app.schemas.managed_service import ManagedServiceResponse

        fields = ManagedServiceResponse.model_fields
        assert "connected_apps" in fields

    def test_connected_apps_default_empty(self):
        """connected_apps should default to empty list."""
        from app.schemas.managed_service import ManagedServiceResponse

        assert ManagedServiceResponse.model_fields["connected_apps"].default == []

    def test_connected_app_summary(self):
        """ConnectedAppSummary should have slug and name."""
        from app.schemas.managed_service import ConnectedAppSummary

        app = ConnectedAppSummary(slug="my-api", name="My API")
        assert app.slug == "my-api"
        assert app.name == "My API"


# ---------------------------------------------------------------------------
# Endpoint signature tests
# ---------------------------------------------------------------------------


class TestEndpointSignatures:
    def test_sync_endpoint_accepts_body(self):
        """POST /sync should accept SyncOptions body."""
        from app.routers.deployments import sync_app

        sig = inspect.signature(sync_app)
        assert "body" in sig.parameters

    def test_sync_diff_endpoint_exists(self):
        """GET /sync-diff endpoint should exist."""
        from app.routers.deployments import get_sync_diff

        assert callable(get_sync_diff)
