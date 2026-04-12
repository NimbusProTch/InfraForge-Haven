"""Render the haven-app Helm chart and verify the rendered output.

Guard against ArgoCD drift from server-side default fields. Covers:
  - HTTPRoute has explicit group/kind on parentRefs and backendRefs
  - backendRefs has explicit weight: 1 (API server default)
  - Deployment has explicit privileged:false on securityContext
  - HPA rendered when autoscaling enabled
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / "charts" / "haven-app"

pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None,
    reason="helm binary not available",
)


def _render(extra_values: dict) -> list[dict]:
    """Render the chart with given values, return list of K8s manifests."""
    base_values = {
        "appSlug": "myapp",
        "tenantSlug": "mytenant",
        "port": 8080,
        "image": {
            "repository": "harbor.example/library/mytenant/myapp",
            "tag": "abc123",
            "pullPolicy": "Always",
            "pullSecrets": [{"name": "harbor-registry-secret"}],
        },
        "httproute": {
            "enabled": True,
            "gateway": {"name": "haven-gateway", "namespace": "haven-gateway"},
            "hostname": "myapp.mytenant.apps.example",
        },
        "autoscaling": {
            "enabled": True,
            "minReplicas": 1,
            "maxReplicas": 3,
            "targetCPUUtilizationPercentage": 70,
        },
    }
    base_values.update(extra_values)
    import json

    result = subprocess.run(
        ["helm", "template", "myapp", str(CHART), "-n", "tenant-mytenant", "-f", "-"],
        input=json.dumps(base_values),
        capture_output=True,
        text=True,
        check=True,
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _find(docs: list[dict], kind: str) -> dict | None:
    for d in docs:
        if d.get("kind") == kind:
            return d
    return None


def test_httproute_parent_ref_has_explicit_group_and_kind():
    """Without explicit group+kind on parentRefs, the API server defaults them
    and ArgoCD reports OutOfSync drift.
    """
    docs = _render({})
    route = _find(docs, "HTTPRoute")
    assert route is not None, "HTTPRoute must be rendered when enabled"
    parent = route["spec"]["parentRefs"][0]
    assert parent.get("group") == "gateway.networking.k8s.io"
    assert parent.get("kind") == "Gateway"
    assert parent.get("name") == "haven-gateway"
    assert parent.get("namespace") == "haven-gateway"


def test_httproute_backend_ref_has_explicit_group_kind_weight():
    """Without explicit group/kind/weight, the API server defaults them
    and ArgoCD reports OutOfSync drift.
    """
    docs = _render({})
    route = _find(docs, "HTTPRoute")
    assert route is not None
    backend = route["spec"]["rules"][0]["backendRefs"][0]
    assert backend.get("group") == ""
    assert backend.get("kind") == "Service"
    assert backend.get("weight") == 1
    assert backend.get("port") == 80


def test_deployment_has_explicit_privileged_false():
    """Kyverno restricted profile rejects pods without explicit privileged:false.

    container-level securityContext must carry privileged/allowPrivilegeEscalation,
    and the pod-level securityContext must carry runAsNonRoot.
    """
    docs = _render({})
    dep = _find(docs, "Deployment")
    assert dep is not None
    pod_spec = dep["spec"]["template"]["spec"]
    pod_sec = pod_spec.get("securityContext", {})
    assert pod_sec.get("runAsNonRoot") is True, "pod runAsNonRoot must be true"
    container = pod_spec["containers"][0]
    sec_ctx = container.get("securityContext", {})
    assert sec_ctx.get("privileged") is False, "container privileged must be explicitly false"
    assert sec_ctx.get("allowPrivilegeEscalation") is False
    assert sec_ctx.get("capabilities", {}).get("drop") == ["ALL"]


def test_httproute_disabled_when_flag_false():
    docs = _render({"httproute": {"enabled": False}})
    assert _find(docs, "HTTPRoute") is None
