"""Static checks that guard the Haven 15/15 sprint fixes.

These tests parse the IaC + cloud-init templates and assert invariants
that the multi-AZ and privatenetworking remediation depends on. They run
without a live cluster: the cluster-side assertions use sample node
fixtures from api/tests/fixtures/.

Why this exists: once the cluster is rebuilt and Haven shows 15/15, the
only thing that can silently regress the score is a drive-by edit to
one of these templates. Static assertions catch that in CI before any
apply even runs.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"


def _load_nodes(fixture_name: str) -> list[dict]:
    data = json.loads((FIXTURES / fixture_name).read_text())
    return data["items"]


def _distinct_zones(nodes: list[dict]) -> set[str]:
    return {n["metadata"]["labels"].get("topology.kubernetes.io/zone", "") for n in nodes}


def _has_external_ip(node: dict) -> bool:
    return any(addr.get("type") == "ExternalIP" for addr in node.get("status", {}).get("addresses", []))


# ---------------------------------------------------------------------------
#  Cluster-side assertions (fixture-driven)
# ---------------------------------------------------------------------------


def test_haven_passing_fixture_has_two_distinct_zones():
    nodes = _load_nodes("sample_nodes_haven_passing.json")
    zones = _distinct_zones(nodes)
    assert len(zones) >= 2, f"Haven infraMultiAZ requires ≥2 distinct zones, got {zones}"


def test_haven_passing_fixture_has_no_external_ip():
    nodes = _load_nodes("sample_nodes_haven_passing.json")
    offenders = [n["metadata"]["name"] for n in nodes if _has_external_ip(n)]
    assert not offenders, f"Haven privatenetworking requires no ExternalIP, offenders: {offenders}"


def test_single_zone_fixture_fails_multiaz():
    nodes = _load_nodes("sample_nodes_single_zone.json")
    assert len(_distinct_zones(nodes)) < 2


def test_external_ip_fixture_fails_privatenetworking():
    nodes = _load_nodes("sample_nodes_with_external_ip.json")
    assert any(_has_external_ip(n) for n in nodes)


# ---------------------------------------------------------------------------
#  IaC-side assertions (template / tfvars parsing)
# ---------------------------------------------------------------------------


def test_prod_tfvars_worker_location_differs_from_location_primary():
    tfvars = (REPO_ROOT / "infrastructure" / "environments" / "prod" / "prod.auto.tfvars").read_text()
    assignments = {}
    for line in tfvars.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, value = stripped.partition("=")
            assignments[key.strip()] = value.strip().strip('"')
    assert assignments.get("location_primary") == "fsn1"
    assert assignments.get("worker_location") == "nbg1"
    assert assignments["worker_location"] != assignments["location_primary"]


def test_rke2_config_template_has_no_node_external_ip():
    template = (
        REPO_ROOT / "infrastructure" / "modules" / "rke2-cluster" / "templates" / "rke2-config.yaml.tpl"
    ).read_text()
    non_comment_lines = [line for line in template.splitlines() if not line.lstrip().startswith("#")]
    for line in non_comment_lines:
        assert not line.lstrip().startswith("node-external-ip:"), (
            "rke2-config.yaml.tpl must not set node-external-ip (Haven "
            "privatenetworking): Hetzner CCM would override it anyway."
        )


def test_rke2_config_template_has_no_public_ip_placeholder():
    template = (
        REPO_ROOT / "infrastructure" / "modules" / "rke2-cluster" / "templates" / "rke2-config.yaml.tpl"
    ).read_text()
    non_comment_lines = [line for line in template.splitlines() if not line.lstrip().startswith("#")]
    payload = "\n".join(non_comment_lines)
    assert "__PUBLIC_IP__" not in payload, (
        "__PUBLIC_IP__ placeholder must be gone — cluster nodes have no public IPv4 (Haven privatenetworking)."
    )


def test_master_cloud_init_does_not_detect_public_ip():
    template = (
        REPO_ROOT / "infrastructure" / "modules" / "rke2-cluster" / "templates" / "master-cloud-init.yaml.tpl"
    ).read_text()
    assert "PUBLIC_IP=" not in template, (
        "master cloud-init must not declare a PUBLIC_IP shell variable — cluster nodes have no public IPv4."
    )
    assert "metadata/public-ipv4" not in template, "master cloud-init must not call Hetzner metadata for public IPv4."


def test_cilium_config_mtu_override_set_to_1450():
    template = (
        REPO_ROOT / "infrastructure" / "modules" / "rke2-cluster" / "manifests" / "rke2-cilium-config.yaml.tpl"
    ).read_text()
    # Cilium helm key is capital MTU — lowercase mtu is silently ignored.
    # 1450 matches Hetzner's private network underlay; Cilium subtracts
    # its own vxlan overhead to set the pod interface MTU internally.
    assert "MTU: 1450" in template, "Cilium must set MTU: 1450 (capital key) to match Hetzner private network underlay."


def test_hetzner_infra_module_declares_nat_server():
    nat_tf = (REPO_ROOT / "infrastructure" / "modules" / "hetzner-infra" / "nat.tf").read_text()
    assert 'resource "hcloud_server" "nat"' in nat_tf, (
        "hetzner-infra module must declare hcloud_server.nat as the egress gateway for public-IP-less cluster nodes."
    )
    assert 'resource "hcloud_network_route" "default_via_nat"' in nat_tf, (
        "hetzner-infra module must declare the default network route via NAT."
    )
