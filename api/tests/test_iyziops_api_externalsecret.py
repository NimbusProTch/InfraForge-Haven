"""Contract tests for the 2.V.3 iyziops-api ExternalSecret manifest.

Locks the four-field partial cutover of `iyziops-api-secrets`: DATABASE_URL,
GITHUB_CLIENT_SECRET, SECRET_KEY, WEBHOOK_SECRET. A typo in a Vault path, a
wrong store reference, or an accidental `creationPolicy: Owner` would either
fail silently (ESO logs a warning) or replace the entire K8s Secret with
only these four keys, crashing iyziops-api on the next pod restart.

These tests are cheap (YAML parse only) and run on every PR.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    REPO_ROOT / "platform" / "argocd" / "apps" / "platform" / "external-secrets-config" / "iyziops-api-secrets.yaml"
)

EXPECTED_SECRET_KEYS = {
    "DATABASE_URL": ("platform/iyziops-api/database", "url"),
    "GITHUB_CLIENT_SECRET": ("platform/iyziops-api/github-repo-oauth", "client_secret"),
    "SECRET_KEY": ("platform/iyziops-api/session-secret", "value"),
    "WEBHOOK_SECRET": ("platform/iyziops-api/webhook-secret", "value"),
}


def _load() -> dict:
    docs = [d for d in yaml.safe_load_all(MANIFEST.read_text()) if d is not None]
    assert len(docs) == 1, f"{MANIFEST} must contain exactly one YAML document"
    return docs[0]


def test_manifest_exists_and_parses() -> None:
    assert MANIFEST.is_file(), f"missing manifest: {MANIFEST}"
    _load()


def test_manifest_is_externalsecret_v1beta1() -> None:
    doc = _load()
    assert doc["apiVersion"] == "external-secrets.io/v1beta1"
    assert doc["kind"] == "ExternalSecret"
    assert doc["metadata"]["name"] == "iyziops-api-secrets-vault"
    assert doc["metadata"]["namespace"] == "haven-system"


def test_manifest_targets_existing_cluster_secret_store() -> None:
    """Must reference the CSS deployed in PR #178."""
    doc = _load()
    ref = doc["spec"]["secretStoreRef"]
    assert ref["name"] == "vault-backend"
    assert ref["kind"] == "ClusterSecretStore"


def test_target_preserves_existing_secret_via_merge() -> None:
    """creationPolicy MUST be Merge for 2.V.3 — the Secret still has five
    plaintext fields (EVEREST/GITEA/GITHUB_CLIENT_ID/HARBOR/KEYCLOAK) that
    other 2.V.* phases own. Owner would strip them and crash the pod."""
    doc = _load()
    target = doc["spec"]["target"]
    assert target["name"] == "iyziops-api-secrets"
    assert target["creationPolicy"] == "Merge", (
        f"creationPolicy MUST be Merge during partial cutover, got "
        f"{target['creationPolicy']!r}. Switching to Owner here would "
        f"drop the five plaintext fields and crash iyziops-api."
    )
    assert target["deletionPolicy"] == "Retain", (
        "deletionPolicy MUST be Retain so rollback (ExternalSecret delete) "
        "does not strip the managed fields and crash the pod."
    )


def test_target_template_annotations_prevent_argocd_prune_loop() -> None:
    """PR #180 shipped without `spec.target.template.metadata.annotations`.
    Result: ESO propagated the ExternalSecret's `argocd.argoproj.io/instance`
    tracking label onto the managed Secret, ArgoCD saw the Secret as an
    extraneous managed resource (tracking label present, no Secret manifest
    in the source path), and pruned it within 2s of every ESO create →
    ESO then errored `Merge: desired secret not found, will not create` →
    the pod crash-looped on an empty DATABASE_URL.

    Fix (this commit): add IgnoreExtraneous on the template so the materialized
    Secret carries the annotation and ArgoCD leaves it alone. This test locks
    the fix so the annotations can't silently drop on a future refactor."""
    doc = _load()
    template_annotations = doc["spec"]["target"]["template"]["metadata"]["annotations"]
    assert template_annotations.get("argocd.argoproj.io/compare-options") == "IgnoreExtraneous", (
        "Missing IgnoreExtraneous — ArgoCD will prune the ESO-managed Secret."
    )
    assert template_annotations.get("argocd.argoproj.io/sync-options") == "Prune=false", (
        "Missing Prune=false — belt-and-braces guard against ArgoCD prune."
    )


def test_data_entries_match_expected_vault_paths() -> None:
    """Every rotated/migrated field must map to its documented Vault path
    + property per docs/audits/bolge-2v-secrets-2026-04-21.md §1."""
    doc = _load()
    actual = {
        entry["secretKey"]: (entry["remoteRef"]["key"], entry["remoteRef"]["property"]) for entry in doc["spec"]["data"]
    }
    assert actual == EXPECTED_SECRET_KEYS, f"Vault path drift. Expected {EXPECTED_SECRET_KEYS}, got {actual}."


def test_data_does_not_leak_other_iyziops_api_fields() -> None:
    """2.V.3 owns only 4 fields. Including any of the 5 plaintext fields
    (EVEREST_ADMIN_PASSWORD etc.) here would accidentally pull them into
    ESO's managed set before their own 2.V.* phase ships their Vault path."""
    doc = _load()
    managed = {entry["secretKey"] for entry in doc["spec"]["data"]}
    out_of_scope = {
        "EVEREST_ADMIN_PASSWORD",
        "GITEA_ADMIN_TOKEN",
        "GITHUB_CLIENT_ID",
        "HARBOR_ADMIN_PASSWORD",
        "KEYCLOAK_ADMIN_PASSWORD",
    }
    overlap = managed & out_of_scope
    assert not overlap, (
        f"2.V.3 accidentally manages fields owned by later phases: {overlap}. "
        f"Remove them until their migration PR lands."
    )
