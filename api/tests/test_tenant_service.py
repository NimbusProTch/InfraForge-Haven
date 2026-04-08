"""Tests for TenantService: ApplicationSet create/delete + cascade deprovision.

Covers:
  - _create_applicationset: renders Jinja2 template, applies via K8s API
  - _delete_applicationset: deletes from ArgoCD namespace
  - provision: includes ApplicationSet creation
  - deprovision: includes ApplicationSet deletion
  - Tenant delete cascade: managed services deprovision
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from kubernetes.client.exceptions import ApiException

from app.services.tenant_service import TenantService


def _make_k8s(available: bool = True) -> MagicMock:
    k8s = MagicMock()
    k8s.is_available.return_value = available
    k8s.core_v1 = MagicMock() if available else None
    k8s.apps_v1 = MagicMock() if available else None
    k8s.rbac_v1 = MagicMock() if available else None
    k8s.custom_objects = MagicMock() if available else None
    if available:
        k8s.custom_objects.create_namespaced_custom_object.return_value = {}
        k8s.custom_objects.delete_namespaced_custom_object.return_value = {}
    return k8s


def _make_harbor_mock() -> MagicMock:
    harbor = MagicMock()
    harbor.create_project = AsyncMock()
    harbor.delete_project = AsyncMock()
    harbor.create_robot_account = AsyncMock(return_value={"name": "robot", "secret": "pass"})
    harbor.build_imagepull_secret = MagicMock(
        return_value={
            "metadata": {"name": "harbor-registry-secret"},
            "type": "kubernetes.io/dockerconfigjson",
            "data": {".dockerconfigjson": "e30="},
        }
    )
    return harbor


# ---------------------------------------------------------------------------
# ApplicationSet creation
# ---------------------------------------------------------------------------


class TestCreateApplicationSet:
    @pytest.mark.asyncio
    async def test_creates_appset_via_k8s_api(self):
        k8s = _make_k8s()
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._create_applicationset("test-tenant")

        k8s.custom_objects.create_namespaced_custom_object.assert_called_once()
        call_kwargs = k8s.custom_objects.create_namespaced_custom_object.call_args.kwargs
        assert call_kwargs["group"] == "argoproj.io"
        assert call_kwargs["namespace"] == "argocd"
        assert call_kwargs["plural"] == "applicationsets"

    @pytest.mark.asyncio
    async def test_appset_name_follows_convention(self):
        k8s = _make_k8s()
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._create_applicationset("gemeente-a")

        body = k8s.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
        assert body["metadata"]["name"] == "appset-gemeente-a"

    @pytest.mark.asyncio
    async def test_appset_has_tenant_labels(self):
        k8s = _make_k8s()
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._create_applicationset("acme")

        body = k8s.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
        labels = body["metadata"]["labels"]
        assert labels["haven.io/managed"] == "true"
        assert labels["haven.io/tenant"] == "acme"
        assert labels["haven.io/type"] == "tenant-apps"

    @pytest.mark.asyncio
    async def test_appset_git_generator_watches_tenant_path(self):
        k8s = _make_k8s()
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._create_applicationset("demo")

        body = k8s.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
        gen = body["spec"]["generators"][0]["git"]
        paths = [d["path"] for d in gen["directories"]]
        assert "tenants/demo/*" in paths

    @pytest.mark.asyncio
    async def test_appset_uses_multi_source(self):
        k8s = _make_k8s()
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._create_applicationset("demo")

        body = k8s.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
        sources = body["spec"]["template"]["spec"]["sources"]
        assert len(sources) == 2
        assert sources[0]["path"] == "charts/haven-app"
        assert sources[1].get("ref") == "values"

    @pytest.mark.asyncio
    async def test_appset_destination_namespace(self):
        k8s = _make_k8s()
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._create_applicationset("utrecht")

        body = k8s.custom_objects.create_namespaced_custom_object.call_args.kwargs["body"]
        dest = body["spec"]["template"]["spec"]["destination"]["namespace"]
        assert dest == "tenant-utrecht"

    @pytest.mark.asyncio
    async def test_appset_409_conflict_is_idempotent(self):
        k8s = _make_k8s()
        k8s.custom_objects.create_namespaced_custom_object.side_effect = ApiException(status=409)
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        # Should not raise
        await svc._create_applicationset("test")

    @pytest.mark.asyncio
    async def test_appset_skipped_when_k8s_unavailable(self):
        k8s = _make_k8s(available=False)
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._create_applicationset("test")
        # No exception, no API call


# ---------------------------------------------------------------------------
# ApplicationSet deletion
# ---------------------------------------------------------------------------


class TestDeleteApplicationSet:
    @pytest.mark.asyncio
    async def test_deletes_appset(self):
        k8s = _make_k8s()
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._delete_applicationset("test-tenant")

        k8s.custom_objects.delete_namespaced_custom_object.assert_called_once_with(
            group="argoproj.io",
            version="v1alpha1",
            namespace="argocd",
            plural="applicationsets",
            name="appset-test-tenant",
        )

    @pytest.mark.asyncio
    async def test_delete_404_is_silent(self):
        k8s = _make_k8s()
        k8s.custom_objects.delete_namespaced_custom_object.side_effect = ApiException(status=404)
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        # Should not raise
        await svc._delete_applicationset("nonexistent")

    @pytest.mark.asyncio
    async def test_delete_skipped_when_k8s_unavailable(self):
        k8s = _make_k8s(available=False)
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._delete_applicationset("test")

    @pytest.mark.asyncio
    async def test_delete_cascades_child_applications(self):
        """ApplicationSet delete should also clean up labeled child Applications."""
        k8s = _make_k8s()
        # Mock list_namespaced_custom_object to return 2 child Applications
        k8s.custom_objects.list_namespaced_custom_object.return_value = {
            "items": [
                {"metadata": {"name": "appset-test-app1"}},
                {"metadata": {"name": "appset-test-app2"}},
            ]
        }
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._delete_applicationset("test")

        # list called with tenant label selector
        k8s.custom_objects.list_namespaced_custom_object.assert_called_once_with(
            group="argoproj.io",
            version="v1alpha1",
            namespace="argocd",
            plural="applications",
            label_selector="haven.io/tenant=test",
        )
        # delete called for each child + the ApplicationSet itself = 3 times
        assert k8s.custom_objects.delete_namespaced_custom_object.call_count == 3

    @pytest.mark.asyncio
    async def test_delete_retries_on_transient_failure(self):
        """ApplicationSet delete should retry up to 3 times on transient 500 errors."""
        k8s = _make_k8s()
        # First 2 attempts fail with 500, 3rd succeeds
        call_count = {"n": 0}

        def _delete(**kwargs):
            if kwargs.get("name", "").startswith("appset-"):
                call_count["n"] += 1
                if call_count["n"] < 3:
                    raise ApiException(status=500, reason="Transient error")
                return None
            return None

        k8s.custom_objects.delete_namespaced_custom_object.side_effect = _delete
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._delete_applicationset("retry-test")

        # Should have retried — total 3 attempts on the ApplicationSet
        assert call_count["n"] == 3

    @pytest.mark.asyncio
    async def test_delete_force_after_all_retries_fail(self):
        """After 3 regular attempts fail, should try force delete with grace_period_seconds=0."""
        k8s = _make_k8s()
        all_attempts = []

        def _delete(**kwargs):
            if kwargs.get("name", "").startswith("appset-"):
                all_attempts.append(kwargs)
                # Force delete has grace_period_seconds — succeed on that
                if kwargs.get("grace_period_seconds") == 0:
                    return None
                raise ApiException(status=500, reason="Stuck")
            return None

        k8s.custom_objects.delete_namespaced_custom_object.side_effect = _delete
        svc = TenantService(k8s, harbor=_make_harbor_mock())
        await svc._delete_applicationset("force-test")

        # Should see regular attempts + force delete
        regular = [a for a in all_attempts if "grace_period_seconds" not in a]
        force = [a for a in all_attempts if a.get("grace_period_seconds") == 0]
        assert len(regular) >= 1  # At least one regular attempt
        assert len(force) == 1  # One force delete


# ---------------------------------------------------------------------------
# Deprovision includes ApplicationSet deletion
# ---------------------------------------------------------------------------


class TestDeprovisionIncludesAppSet:
    @pytest.mark.asyncio
    async def test_deprovision_deletes_appset_before_namespace(self):
        k8s = _make_k8s()
        svc = TenantService(k8s, harbor=_make_harbor_mock())

        call_order = []
        k8s.custom_objects.delete_namespaced_custom_object.side_effect = lambda **kw: call_order.append("appset")
        original_delete_ns = k8s.core_v1.delete_namespace
        k8s.core_v1.delete_namespace = lambda ns: call_order.append("namespace")

        await svc.deprovision("tenant-test", slug="test")

        assert "appset" in call_order
        assert "namespace" in call_order
        assert call_order.index("appset") < call_order.index("namespace")
