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
    ARGOCD_LOCAL_ACCOUNT,
    ARGOCD_NAMESPACE,
    ARGOCD_RBAC_LINES,
    ARGOCD_TOKEN_SECRET_NAME,
    ARGOCD_TOKEN_SECRET_NAMESPACE,
    _patch_argocd_cm_account,
    _patch_argocd_rbac_policy,
    _patch_argocd_secret_password,
    _read_existing_argocd_token,
    _trigger_iyziops_api_rollout,
    _write_token_secret,
    ensure_argocd_api_token,
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


# ---------------------------------------------------------------------------
# ArgoCD `iyziops-api` local account + persistent API token bootstrap tests
# ---------------------------------------------------------------------------


def _fake_v1_secret(data: dict | None = None):
    """Build a minimal V1Secret stand-in mock."""
    s = MagicMock()
    s.data = data or {}
    s.metadata = MagicMock()
    return s


def _fake_v1_cm(data: dict | None = None):
    cm = MagicMock()
    cm.data = data or {}
    return cm


def test_read_existing_argocd_token_returns_none_when_secret_missing():
    fake_core = MagicMock()
    fake_core.read_namespaced_secret.side_effect = ApiException(status=404, reason="NotFound")
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.core_v1 = fake_core
        assert _read_existing_argocd_token() is None


def test_read_existing_argocd_token_returns_decoded_value():
    import base64

    fake_core = MagicMock()
    fake_core.read_namespaced_secret.return_value = _fake_v1_secret(
        data={"token": base64.b64encode(b"abc.def.ghi").decode()}
    )
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.core_v1 = fake_core
        assert _read_existing_argocd_token() == "abc.def.ghi"


def test_patch_argocd_cm_account_no_op_when_already_set():
    fake_core = MagicMock()
    fake_core.read_namespaced_config_map.return_value = _fake_v1_cm(
        data={f"accounts.{ARGOCD_LOCAL_ACCOUNT}": "apiKey,login"}
    )
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.core_v1 = fake_core
        _patch_argocd_cm_account()
    fake_core.replace_namespaced_config_map.assert_not_called()


def test_patch_argocd_cm_account_writes_when_missing():
    fake_core = MagicMock()
    fake_core.read_namespaced_config_map.return_value = _fake_v1_cm(data={})
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.core_v1 = fake_core
        _patch_argocd_cm_account()
    fake_core.replace_namespaced_config_map.assert_called_once()
    new_cm = fake_core.replace_namespaced_config_map.call_args[0][2]
    assert new_cm.data[f"accounts.{ARGOCD_LOCAL_ACCOUNT}"] == "apiKey,login"


def test_patch_argocd_secret_password_writes_bcrypt_hash():
    import base64

    import bcrypt

    fake_core = MagicMock()
    fake_core.read_namespaced_secret.return_value = _fake_v1_secret(data={})
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.core_v1 = fake_core
        _patch_argocd_secret_password("super-secret-password")
    fake_core.replace_namespaced_secret.assert_called_once()
    new_secret = fake_core.replace_namespaced_secret.call_args[0][2]
    pw_b64 = new_secret.data[f"accounts.{ARGOCD_LOCAL_ACCOUNT}.password"]
    pw_hash = base64.b64decode(pw_b64)
    # bcrypt.checkpw returns True iff the plaintext matches the hash
    assert bcrypt.checkpw(b"super-secret-password", pw_hash)
    # passwordMtime must be set
    assert f"accounts.{ARGOCD_LOCAL_ACCOUNT}.passwordMtime" in new_secret.data


def test_patch_argocd_rbac_policy_appends_role_and_binding():
    fake_core = MagicMock()
    fake_core.read_namespaced_config_map.return_value = _fake_v1_cm(
        data={"policy.csv": "p, role:admin, *, *, */*, allow\n"}
    )
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.core_v1 = fake_core
        _patch_argocd_rbac_policy()
    fake_core.replace_namespaced_config_map.assert_called_once()
    new_cm = fake_core.replace_namespaced_config_map.call_args[0][2]
    csv = new_cm.data["policy.csv"]
    for line in ARGOCD_RBAC_LINES:
        assert line in csv, f"missing {line!r} in policy.csv"
    # Existing admin policy must be preserved
    assert "p, role:admin, *, *, */*, allow" in csv


def test_patch_argocd_rbac_policy_no_op_when_role_already_present():
    fake_core = MagicMock()
    fake_core.read_namespaced_config_map.return_value = _fake_v1_cm(
        data={"policy.csv": f"g, {ARGOCD_LOCAL_ACCOUNT}, role:{ARGOCD_LOCAL_ACCOUNT}\n"}
    )
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.core_v1 = fake_core
        _patch_argocd_rbac_policy()
    fake_core.replace_namespaced_config_map.assert_not_called()


def test_write_token_secret_creates_when_missing_returns_true():
    fake_core = MagicMock()
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.core_v1 = fake_core
        result = _write_token_secret("the.persistent.token")
    assert result is True, "fresh create must return True so caller triggers rollout"
    fake_core.create_namespaced_secret.assert_called_once()
    args, _kw = fake_core.create_namespaced_secret.call_args
    assert args[0] == ARGOCD_TOKEN_SECRET_NAMESPACE
    body = args[1]
    assert body.metadata.name == ARGOCD_TOKEN_SECRET_NAME
    import base64

    assert base64.b64decode(body.data["token"]).decode() == "the.persistent.token"


def test_write_token_secret_replaces_on_409_returns_false():
    fake_core = MagicMock()
    fake_core.create_namespaced_secret.side_effect = ApiException(status=409, reason="AlreadyExists")
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.core_v1 = fake_core
        result = _write_token_secret("the.token")
    assert result is False, "replace path must return False (no rollout needed — pod already has env)"
    fake_core.replace_namespaced_secret.assert_called_once()


def test_trigger_iyziops_api_rollout_patches_pod_template_annotation():
    """Self-rollout patches the pod template's `restartedAt` annotation —
    same shape `kubectl rollout restart deploy/iyziops-api` produces."""
    fake_apps = MagicMock()
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.apps_v1 = fake_apps
        _trigger_iyziops_api_rollout()
    fake_apps.patch_namespaced_deployment.assert_called_once()
    kwargs = fake_apps.patch_namespaced_deployment.call_args.kwargs
    assert kwargs["name"] == "iyziops-api"
    assert kwargs["namespace"] == ARGOCD_TOKEN_SECRET_NAMESPACE
    annotations = kwargs["body"]["spec"]["template"]["metadata"]["annotations"]
    assert "kubectl.kubernetes.io/restartedAt" in annotations
    assert annotations["haven.io/restart-reason"] == "argocd-token-bootstrap"


def test_trigger_iyziops_api_rollout_skips_when_apps_v1_unavailable():
    """Defensive: if K8s client never initialized, swallow gracefully."""
    with patch("app.services.platform_bootstrap.k8s_client") as k8s:
        k8s.apps_v1 = None
        # Must not raise
        _trigger_iyziops_api_rollout()


@pytest.mark.asyncio
async def test_ensure_argocd_api_token_short_circuits_when_secret_already_has_token():
    """If the Secret already has a non-empty token we must not contact ArgoCD again."""
    with (
        patch(
            "app.services.platform_bootstrap._read_existing_argocd_token",
            return_value="existing.jwt.token",
        ),
        patch("app.services.platform_bootstrap._patch_argocd_cm_account") as cm_patch,
        patch("app.services.platform_bootstrap._argocd_login_and_mint_token") as mint,
        patch("app.services.platform_bootstrap.k8s_client") as k8s,
        patch("app.services.platform_bootstrap.settings") as s,
    ):
        k8s.is_available.return_value = True
        k8s.core_v1 = MagicMock()
        s.argocd_url = "http://argocd-server.argocd.svc:80"
        await ensure_argocd_api_token()
    cm_patch.assert_not_called()
    mint.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_argocd_api_token_full_flow_writes_secret_and_triggers_rollout():
    """Happy path: no existing token → patch CM/Secret/RBAC → login → mint → write Secret → self-rollout."""
    with (
        patch("app.services.platform_bootstrap._read_existing_argocd_token", return_value=None),
        patch("app.services.platform_bootstrap._patch_argocd_cm_account") as cm_patch,
        patch("app.services.platform_bootstrap._patch_argocd_secret_password") as pw_patch,
        patch("app.services.platform_bootstrap._patch_argocd_rbac_policy") as rbac_patch,
        patch(
            "app.services.platform_bootstrap._argocd_login_and_mint_token",
            new=AsyncMock(return_value="minted.jwt.token"),
        ) as mint,
        patch("app.services.platform_bootstrap._write_token_secret", return_value=True) as write_secret,
        patch("app.services.platform_bootstrap._trigger_iyziops_api_rollout") as rollout,
        patch("app.services.platform_bootstrap.asyncio.sleep", new=AsyncMock()),
        patch("app.services.platform_bootstrap.k8s_client") as k8s,
        patch("app.services.platform_bootstrap.settings") as s,
    ):
        k8s.is_available.return_value = True
        k8s.core_v1 = MagicMock()
        s.argocd_url = "http://argocd-server.argocd.svc:80"
        await ensure_argocd_api_token()
    cm_patch.assert_called_once()
    pw_patch.assert_called_once()
    rbac_patch.assert_called_once()
    mint.assert_awaited_once()
    write_secret.assert_called_once_with("minted.jwt.token")
    rollout.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_argocd_api_token_skips_rollout_when_secret_already_existed():
    """If the Secret was just replaced (not freshly created), the running pod
    already has the env var bound and we don't need a rollout."""
    with (
        patch("app.services.platform_bootstrap._read_existing_argocd_token", return_value=None),
        patch("app.services.platform_bootstrap._patch_argocd_cm_account"),
        patch("app.services.platform_bootstrap._patch_argocd_secret_password"),
        patch("app.services.platform_bootstrap._patch_argocd_rbac_policy"),
        patch(
            "app.services.platform_bootstrap._argocd_login_and_mint_token",
            new=AsyncMock(return_value="rotated.jwt.token"),
        ),
        patch("app.services.platform_bootstrap._write_token_secret", return_value=False),
        patch("app.services.platform_bootstrap._trigger_iyziops_api_rollout") as rollout,
        patch("app.services.platform_bootstrap.asyncio.sleep", new=AsyncMock()),
        patch("app.services.platform_bootstrap.k8s_client") as k8s,
        patch("app.services.platform_bootstrap.settings") as s,
    ):
        k8s.is_available.return_value = True
        k8s.core_v1 = MagicMock()
        s.argocd_url = "http://argocd-server.argocd.svc:80"
        await ensure_argocd_api_token()
    rollout.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_argocd_api_token_skips_when_argocd_url_empty():
    with (
        patch("app.services.platform_bootstrap.k8s_client") as k8s,
        patch("app.services.platform_bootstrap.settings") as s,
        patch("app.services.platform_bootstrap._patch_argocd_cm_account") as cm_patch,
    ):
        k8s.is_available.return_value = True
        k8s.core_v1 = MagicMock()
        s.argocd_url = ""
        await ensure_argocd_api_token()
    cm_patch.assert_not_called()


@pytest.mark.asyncio
async def test_run_platform_bootstrap_invokes_argocd_api_token():
    """Guard: the top-level orchestrator must call all 3 bootstrap steps."""
    with (
        patch("app.services.platform_bootstrap.ensure_haven_gitops_repo", new=AsyncMock()) as gitea,
        patch("app.services.platform_bootstrap.ensure_argocd_gitea_repo_secret") as repo_sec,
        patch("app.services.platform_bootstrap.ensure_argocd_api_token", new=AsyncMock()) as token_step,
    ):
        await run_platform_bootstrap()
    gitea.assert_awaited_once()
    repo_sec.assert_called_once()
    token_step.assert_awaited_once()


def test_main_lifespan_still_invokes_run_platform_bootstrap():
    """Sanity guard duplicate of test_main_lifespan_invokes_bootstrap — ensures the
    new third bootstrap step doesn't get added without calling run_platform_bootstrap."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "main.py"
    content = src.read_text()
    assert "await run_platform_bootstrap()" in content
