"""Contract tests for the 2.V.2 ClusterSecretStore manifest + appset wiring.

The ClusterSecretStore resource is declarative YAML consumed by the External
Secrets Operator (ESO v0.10.x). A typo in a key name or a wrong apiVersion
surfaces as a runtime sync failure in ArgoCD, which is slow to notice.
These tests lint the manifest structure at code-review time.

The actual end-to-end smoke test (write to Vault → ESO creates K8s Secret)
was performed manually during 2.V.2 bootstrap; see PR body for the evidence
log. Re-running that against live cluster from CI would require a
Vault+kubernetes fixture that does not yet exist.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CSS_MANIFEST = (
    REPO_ROOT / "platform" / "argocd" / "apps" / "platform" / "external-secrets-config" / "cluster-secret-store.yaml"
)
APPSET = REPO_ROOT / "platform" / "argocd" / "appsets" / "platform-raw.yaml"


def _load_single_doc(path: Path) -> dict:
    """Load a one-document YAML file; raise if the file has multiple docs."""
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d is not None]
    assert len(docs) == 1, f"{path} expected to contain exactly one document"
    return docs[0]


def test_css_manifest_exists_and_parses() -> None:
    assert CSS_MANIFEST.is_file(), f"missing manifest: {CSS_MANIFEST}"
    doc = _load_single_doc(CSS_MANIFEST)
    assert doc is not None


def test_css_has_correct_api_version_and_kind() -> None:
    doc = _load_single_doc(CSS_MANIFEST)
    # ESO v0.10 uses external-secrets.io/v1beta1; v1 is the v0.12+ GA API.
    # Using v1beta1 here matches the ESO chart version pinned in
    # platform-helm.yaml (0.10.7).
    assert doc["apiVersion"] == "external-secrets.io/v1beta1"
    assert doc["kind"] == "ClusterSecretStore"
    assert doc["metadata"]["name"] == "vault-backend"


def test_css_points_at_in_cluster_vault() -> None:
    doc = _load_single_doc(CSS_MANIFEST)
    vault = doc["spec"]["provider"]["vault"]
    assert vault["server"] == "http://vault.vault-system.svc.cluster.local:8200"
    assert vault["path"] == "kv"
    assert vault["version"] == "v2"


def test_css_kubernetes_auth_role_matches_vault() -> None:
    """Vault-side role (bootstrapped manually in 2.V.2) is named
    `external-secrets` with bound SA `external-secrets/external-secrets`
    and audience `vault`. Manifest must match all three."""
    doc = _load_single_doc(CSS_MANIFEST)
    k8s = doc["spec"]["provider"]["vault"]["auth"]["kubernetes"]
    assert k8s["role"] == "external-secrets"
    assert k8s["mountPath"] == "kubernetes"
    sa_ref = k8s["serviceAccountRef"]
    assert sa_ref["name"] == "external-secrets"
    assert sa_ref["namespace"] == "external-secrets"
    # Without `audiences: [vault]` the projected token carries the cluster
    # default audience and Vault login returns `invalid audience claim`.
    assert sa_ref["audiences"] == ["vault"]


def test_platform_raw_appset_wires_external_secrets_config() -> None:
    """The appset must enumerate external-secrets-config in its list
    generator, pointing at the dedicated directory path."""
    docs = [d for d in yaml.safe_load_all(APPSET.read_text()) if d is not None]
    appset = next(d for d in docs if d.get("kind") == "ApplicationSet" and d["metadata"]["name"] == "platform-raw")
    elements = appset["spec"]["generators"][0]["list"]["elements"]
    names = {e["name"] for e in elements}
    assert "external-secrets-config" in names, (
        f"platform-raw appset missing external-secrets-config element; currently has: {sorted(names)}"
    )
    entry = next(e for e in elements if e["name"] == "external-secrets-config")
    assert entry["path"] == "platform/argocd/apps/platform/external-secrets-config"
    assert entry["namespace"] == "external-secrets"
    assert entry["syncWave"] == "1"
