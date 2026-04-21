"""Lock the ClusterSecretStore / ESO apiVersion constants used by SecretService.

PR #178 deployed the `vault-backend` ClusterSecretStore at
`platform/argocd/apps/platform/external-secrets-config/cluster-secret-store.yaml`
using apiVersion `external-secrets.io/v1beta1` (matching ESO chart 0.10.7).

`api/app/services/secret_service.py` synthesizes ExternalSecret CRDs for each
tenant app at runtime. Those CRDs must reference the SAME store name and the
SAME apiVersion — otherwise ESO silently skips them (no CSS named <X>) or
K8s API rejects the resource (no CRD version <Y>).

These tests fail fast at code-review time if:
- The constant in secret_service.py drifts from the deployed CSS manifest
- The apiVersion drifts from what the ESO chart serves
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.services.secret_service import (
    _CLUSTER_SECRET_STORE_NAME,
    _ESO_API_VERSION,
    _ESO_CRD_VERSION,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CSS_MANIFEST = (
    REPO_ROOT / "platform" / "argocd" / "apps" / "platform" / "external-secrets-config" / "cluster-secret-store.yaml"
)


def _load_css() -> dict:
    docs = [d for d in yaml.safe_load_all(CSS_MANIFEST.read_text()) if d is not None]
    assert len(docs) == 1, f"{CSS_MANIFEST} must contain exactly one document"
    return docs[0]


def test_secret_service_uses_deployed_cluster_secret_store_name() -> None:
    """The name in code MUST match the name in the committed CSS manifest."""
    css = _load_css()
    assert css["metadata"]["name"] == _CLUSTER_SECRET_STORE_NAME, (
        f"secret_service.py points at `{_CLUSTER_SECRET_STORE_NAME}` but the "
        f"deployed manifest declares `{css['metadata']['name']}`. "
        f"Drift here → ESO reports `ClusterSecretStore not found` on every sync."
    )


def test_secret_service_uses_deployed_eso_api_version() -> None:
    """The apiVersion in code MUST match the apiVersion in the CSS manifest."""
    css = _load_css()
    assert css["apiVersion"] == _ESO_API_VERSION, (
        f"secret_service.py uses apiVersion `{_ESO_API_VERSION}` but the CSS "
        f"manifest declares `{css['apiVersion']}`. Drift → K8s API 404 on "
        f"ExternalSecret create."
    )


def test_eso_api_version_matches_crd_version() -> None:
    """The k8s custom-object client takes group + version separately; they must
    agree with the full apiVersion string `group/version`."""
    assert f"external-secrets.io/{_ESO_CRD_VERSION}" == _ESO_API_VERSION


def test_no_legacy_haven_vault_references_in_services() -> None:
    """`haven-vault` was the pre-2.V.2 store name. If it re-appears anywhere
    in api/app/services/, a cutover has regressed."""
    services_dir = REPO_ROOT / "api" / "app" / "services"
    offenders: list[str] = []
    for py_file in services_dir.rglob("*.py"):
        text = py_file.read_text()
        if "haven-vault" in text:
            offenders.append(str(py_file.relative_to(REPO_ROOT)))
    assert offenders == [], (
        f"Legacy `haven-vault` references still in services: {offenders}. Rename to `vault-backend` (the 2.V.2 store)."
    )


def test_no_legacy_v1_eso_api_references_in_services() -> None:
    """ESO chart 0.10.7 serves only `v1beta1`. Using `/v1` yields a K8s 404."""
    services_dir = REPO_ROOT / "api" / "app" / "services"
    offenders: list[str] = []
    for py_file in services_dir.rglob("*.py"):
        for lineno, line in enumerate(py_file.read_text().splitlines(), start=1):
            # Match `external-secrets.io/v1` NOT followed by `beta` / `alpha`.
            if "external-secrets.io/v1" in line and "v1beta" not in line and "v1alpha" not in line:
                offenders.append(f"{py_file.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert offenders == [], (
        "Legacy `external-secrets.io/v1` apiVersion found in services:\n"
        + "\n".join(offenders)
        + "\nESO 0.10 serves `v1beta1` only; `/v1` is GA at ESO 0.12+."
    )
