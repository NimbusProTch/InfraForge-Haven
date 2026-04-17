"""Validate platform-helm ApplicationSet entries are active + version-pinned.

Guards against:
- Re-commenting the Everest chart entry (regression after the 2026-04-17 VM
  operator PSA incident when GitOps path first went live).
- Landing on unpinned targetRevision (`<latest>`, empty) that causes silent
  drift across ArgoCD reconciles.
"""

from __future__ import annotations

from pathlib import Path

import yaml

APPSET_PATH = Path(__file__).resolve().parents[2] / "platform" / "argocd" / "appsets" / "platform-helm.yaml"


def _load_elements() -> list[dict]:
    """Parse the platform-helm ApplicationSet and return list-generator elements."""
    text = APPSET_PATH.read_text()
    docs = [d for d in yaml.safe_load_all(text) if d]
    assert len(docs) == 1, f"Expected 1 YAML doc, got {len(docs)}"
    spec = docs[0]["spec"]
    return spec["generators"][0]["list"]["elements"]


def test_everest_entry_active_and_pinned() -> None:
    """Everest Helm app must be active (not commented) with pinned chart version."""
    elements = _load_elements()
    everest = next((e for e in elements if e.get("name") == "everest"), None)
    assert everest is not None, (
        "Everest entry missing from platform-helm AppSet — if it was re-commented, "
        "PG/MySQL/MongoDB provisioning via Everest breaks (see managed_service.py)."
    )
    assert everest["namespace"] == "everest-system"
    assert everest["syncWave"] == "4", "Everest must be in wave 4 (data services)"
    assert everest["chart"] == "everest"
    assert everest["repoURL"] == "https://percona.github.io/percona-helm-charts"
    rev = everest["targetRevision"]
    assert rev not in ("<latest>", "latest", ""), f"targetRevision must be pinned, got {rev!r}"
    assert any(c.isdigit() for c in rev) and "." in rev, f"targetRevision must look like semver, got {rev!r}"


def test_everest_values_disable_monitoring() -> None:
    """Monitoring subcharts must be off — prior CLI installs failed here via PSA."""
    elements = _load_elements()
    everest = next(e for e in elements if e.get("name") == "everest")
    values = yaml.safe_load(everest["values"])
    assert values["monitoring"]["enabled"] is False, (
        "monitoring.enabled MUST be false — VM operator fails with PSA restricted "
        "on everest-monitoring ns (see 3x CLI install incident 2026-04-17)."
    )
    assert values["kube-state-metrics"]["enabled"] is False, (
        "kube-state-metrics subchart lands in everest-monitoring ns and fails PSA."
    )
    assert values["createMonitoringResources"] is False, (
        "ServiceMonitor/PodMonitor creation depends on VM operator CRDs."
    )


def test_all_helm_entries_pinned() -> None:
    """Every active Helm app must have a pinned targetRevision (no floating tags)."""
    for el in _load_elements():
        rev = el.get("targetRevision")
        assert rev not in (None, "<latest>", "latest", ""), f"{el['name']} has unpinned targetRevision={rev!r}"


# ---------------------------------------------------------------------------
# Namespace PSA guard (direct test of the 2026-04-17 regression vector)
# ---------------------------------------------------------------------------

NAMESPACES_PATH = (
    Path(__file__).resolve().parents[2] / "platform" / "argocd" / "apps" / "platform" / "namespaces" / "everest.yaml"
)


def _load_everest_namespaces() -> dict[str, dict]:
    """Parse the everest namespaces manifest and return {name: full-manifest}."""
    text = NAMESPACES_PATH.read_text()
    docs = [d for d in yaml.safe_load_all(text) if d]
    return {d["metadata"]["name"]: d for d in docs}


def test_everest_namespaces_all_privileged() -> None:
    """All 4 everest-* namespaces MUST enforce PSA=privileged.

    The 2026-04-17 incident had `everest-monitoring` created without a PSA label,
    defaulting to cluster `restricted` → VictoriaMetrics operator pod was blocked
    from scheduling (allowPrivilegeEscalation, capabilities.drop, runAsNonRoot,
    seccompProfile). Pre-labeling all four namespaces is the primary fix.
    """
    namespaces = _load_everest_namespaces()
    expected = {"everest", "everest-system", "everest-olm", "everest-monitoring"}
    assert set(namespaces.keys()) == expected, (
        f"Missing: {expected - namespaces.keys()}, extra: {namespaces.keys() - expected}"
    )
    for name, ns in namespaces.items():
        labels = ns["metadata"]["labels"]
        enforce = labels.get("pod-security.kubernetes.io/enforce")
        assert enforce == "privileged", (
            f"{name}: PSA enforce={enforce!r} — MUST be 'privileged' (see 2026-04-17 VM FailedCreate incident)"
        )
        assert labels.get("iyziops.io/layer") == "data-services", f"{name}: missing iyziops.io/layer=data-services"


def test_everest_monitoring_namespace_present_even_if_monitoring_disabled() -> None:
    """everest-monitoring namespace must be pre-labeled even when monitoring off.

    Rationale: the namespace exists to be ready for future monitoring re-enable
    without repeating the PSA debugging cycle. Current chart values keep
    monitoring.enabled=false — this test guards against someone deleting the
    namespace entry when they see it's empty at deploy time.
    """
    namespaces = _load_everest_namespaces()
    assert "everest-monitoring" in namespaces, (
        "everest-monitoring ns manifest missing — re-enabling chart monitoring would repeat the PSA failure"
    )
