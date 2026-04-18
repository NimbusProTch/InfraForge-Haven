"""Tests for iyziops-api platform self-service bootstrap.

The bootstrap exists to close gaps that previously required kubectl / Gitea
API calls during the first cluster bring-up. Fresh-cluster reproducibility
depends on these being idempotent and non-fatal.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kubernetes.client import ApiException

from app.services.platform_bootstrap import (
    ARGOCD_GITEA_SECRET_NAME,
    ARGOCD_NAMESPACE,
    ensure_argocd_gitea_repo_secret,
    ensure_haven_gitops_repo,
    run_platform_bootstrap,
)


@pytest.mark.asyncio
async def test_ensure_haven_gitops_repo_calls_ensure_org_and_repo():
    with patch("app.services.platform_bootstrap.gitea_client") as gitea:
        gitea.ensure_org = AsyncMock()
        gitea.ensure_repo = AsyncMock()
        await ensure_haven_gitops_repo()
        gitea.ensure_org.assert_awaited_once_with("haven")
        gitea.ensure_repo.assert_awaited_once_with("haven", "haven-gitops")


@pytest.mark.asyncio
async def test_ensure_haven_gitops_repo_retries_on_failure():
    calls = {"n": 0}

    async def flaky_org(_):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("gitea unreachable")

    with (
        patch("app.services.platform_bootstrap.gitea_client") as gitea,
        patch("app.services.platform_bootstrap.asyncio.sleep", AsyncMock()),
    ):
        gitea.ensure_org = flaky_org
        gitea.ensure_repo = AsyncMock()
        await ensure_haven_gitops_repo()
        assert calls["n"] == 3
        gitea.ensure_repo.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_haven_gitops_repo_non_fatal_after_3_retries():
    """Persistent failure must not raise — bootstrap is non-fatal."""

    async def always_fail(_):
        raise RuntimeError("gitea down")

    with (
        patch("app.services.platform_bootstrap.gitea_client") as gitea,
        patch("app.services.platform_bootstrap.asyncio.sleep", AsyncMock()),
    ):
        gitea.ensure_org = always_fail
        gitea.ensure_repo = AsyncMock()
        # Must not raise
        await ensure_haven_gitops_repo()


def test_ensure_argocd_secret_creates_when_missing():
    fake_core = MagicMock()
    fake_core.create_namespaced_secret = MagicMock()
    with (
        patch("app.services.platform_bootstrap.k8s_client") as k8s,
        patch("app.services.platform_bootstrap.settings") as s,
    ):
        k8s.is_available.return_value = True
        k8s.core_v1 = fake_core
        s.gitea_admin_token = "abc123"
        s.gitea_url = "http://gitea.svc:3000"
        s.gitea_org = "haven"
        s.gitea_gitops_repo = "haven-gitops"
        ensure_argocd_gitea_repo_secret()
    fake_core.create_namespaced_secret.assert_called_once()
    args, _ = fake_core.create_namespaced_secret.call_args
    assert args[0] == ARGOCD_NAMESPACE
    body = args[1]
    assert body.metadata.name == ARGOCD_GITEA_SECRET_NAME
    assert body.metadata.labels["argocd.argoproj.io/secret-type"] == "repository"
    # URL is built from settings.gitea_url + org + repo (no double slashes, .git suffix)
    import base64

    url = base64.b64decode(body.data["url"]).decode()
    assert url == "http://gitea.svc:3000/haven/haven-gitops.git"
    assert base64.b64decode(body.data["username"]).decode() == "gitea_admin"
    assert base64.b64decode(body.data["password"]).decode() == "abc123"


def test_ensure_argocd_secret_replaces_on_409():
    fake_core = MagicMock()
    fake_core.create_namespaced_secret = MagicMock(side_effect=ApiException(status=409, reason="AlreadyExists"))
    fake_core.replace_namespaced_secret = MagicMock()
    with (
        patch("app.services.platform_bootstrap.k8s_client") as k8s,
        patch("app.services.platform_bootstrap.settings") as s,
    ):
        k8s.is_available.return_value = True
        k8s.core_v1 = fake_core
        s.gitea_admin_token = "abc"
        s.gitea_url = "http://g:3000"
        s.gitea_org = "haven"
        s.gitea_gitops_repo = "haven-gitops"
        ensure_argocd_gitea_repo_secret()
    fake_core.replace_namespaced_secret.assert_called_once()


def test_ensure_argocd_secret_skips_when_token_empty():
    fake_core = MagicMock()
    with (
        patch("app.services.platform_bootstrap.k8s_client") as k8s,
        patch("app.services.platform_bootstrap.settings") as s,
    ):
        k8s.is_available.return_value = True
        k8s.core_v1 = fake_core
        s.gitea_admin_token = ""
        ensure_argocd_gitea_repo_secret()
    fake_core.create_namespaced_secret.assert_not_called()


def test_ensure_argocd_secret_skips_when_k8s_unavailable():
    with (
        patch("app.services.platform_bootstrap.k8s_client") as k8s,
        patch("app.services.platform_bootstrap.settings") as s,
    ):
        k8s.is_available.return_value = False
        k8s.core_v1 = None
        s.gitea_admin_token = "abc"
        # Must not raise
        ensure_argocd_gitea_repo_secret()


@pytest.mark.asyncio
async def test_run_platform_bootstrap_swallows_secret_exception():
    """ArgoCD secret step raising must not prevent return (non-fatal)."""
    with (
        patch("app.services.platform_bootstrap.ensure_haven_gitops_repo", AsyncMock()),
        patch(
            "app.services.platform_bootstrap.ensure_argocd_gitea_repo_secret",
            side_effect=RuntimeError("boom"),
        ),
    ):
        await run_platform_bootstrap()


def test_main_lifespan_invokes_bootstrap():
    """Guard: main.py's lifespan must import + call run_platform_bootstrap."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "main.py"
    content = src.read_text()
    assert "from app.services.platform_bootstrap import run_platform_bootstrap" in content
    assert "await run_platform_bootstrap()" in content
