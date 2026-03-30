"""Tests for the ApplicationSet Jinja2 templates (Sprint I-4).

Covers:
  - App ApplicationSet: correct naming, namespace, chart path, git generator path
  - Service ApplicationSet: correct naming, segment index, service path
  - Naming convention: appset-{slug}, svcset-{slug}, {slug}-<app>, svc-{slug}-<svc>
  - YAML validity: rendered output must be parseable YAML
  - Custom parameters: repo_url, revision, chart_path, gitops_prefix
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Ensure the generator module is importable even without installing the package.
# We add the platform/templates directory to sys.path.
# ---------------------------------------------------------------------------
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "platform" / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

try:
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "tenant_appset_generator",
        TEMPLATES_DIR / "tenant-appset-generator.py",
    )
    assert _spec and _spec.loader
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    render_app_appset = _mod.render_app_appset
    render_svc_appset = _mod.render_svc_appset
    _GENERATOR_AVAILABLE = True
except Exception:
    _GENERATOR_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _GENERATOR_AVAILABLE,
    reason="jinja2 not installed or generator module not importable",
)

TENANT_SLUG = "gemeente-utrecht"
REPO_URL = "https://github.com/NimbusProTch/InfraForge-Haven.git"
REVISION = "main"


# ---------------------------------------------------------------------------
# App ApplicationSet tests
# ---------------------------------------------------------------------------


def test_app_appset_is_valid_yaml():
    """Rendered app ApplicationSet must parse as valid YAML."""
    rendered = render_app_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    docs = list(yaml.safe_load_all(rendered))
    assert len(docs) == 1
    assert docs[0] is not None


def test_app_appset_name_follows_convention():
    """ApplicationSet name must be 'appset-{slug}'."""
    rendered = render_app_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    doc = yaml.safe_load(rendered)
    assert doc["metadata"]["name"] == f"appset-{TENANT_SLUG}"


def test_app_appset_namespace_is_argocd():
    """ApplicationSet must be in the argocd namespace."""
    rendered = render_app_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    doc = yaml.safe_load(rendered)
    assert doc["metadata"]["namespace"] == "argocd"


def test_app_appset_git_generator_path_contains_tenant_slug():
    """Git generator path must reference the tenant's gitops directory."""
    rendered = render_app_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    doc = yaml.safe_load(rendered)

    generators = doc["spec"]["generators"]
    git_gen = next(g for g in generators if "git" in g)
    paths = [d["path"] for d in git_gen["git"]["directories"]]
    assert any(TENANT_SLUG in p for p in paths), f"Expected tenant slug in generator paths: {paths}"


def test_app_appset_excludes_services_directory():
    """App ApplicationSet must exclude services/* from git generator."""
    rendered = render_app_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    doc = yaml.safe_load(rendered)

    generators = doc["spec"]["generators"]
    git_gen = next(g for g in generators if "git" in g)
    excluded = [d["path"] for d in git_gen["git"]["directories"] if d.get("exclude")]
    assert any("services" in p for p in excluded), f"Expected services excluded, got: {excluded}"


def test_app_appset_destination_namespace_is_tenant_namespaced():
    """Destination namespace must be 'tenant-{slug}'."""
    rendered = render_app_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    doc = yaml.safe_load(rendered)
    dest_ns = doc["spec"]["template"]["spec"]["destination"]["namespace"]
    assert dest_ns == f"tenant-{TENANT_SLUG}"


def test_app_appset_uses_custom_chart_path():
    """Custom chart_path parameter must appear in the rendered source.path."""
    custom_chart = "charts/my-custom-chart"
    rendered = render_app_appset(
        TENANT_SLUG,
        chart_repo_url=REPO_URL,
        target_revision=REVISION,
        chart_path=custom_chart,
    )
    doc = yaml.safe_load(rendered)
    sources = doc["spec"]["template"]["spec"]["sources"]
    chart_source = sources[0]  # First source = Helm chart
    assert chart_source["path"] == custom_chart


# ---------------------------------------------------------------------------
# Service ApplicationSet tests
# ---------------------------------------------------------------------------


def test_svc_appset_is_valid_yaml():
    """Rendered service ApplicationSet must parse as valid YAML."""
    rendered = render_svc_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    docs = list(yaml.safe_load_all(rendered))
    assert len(docs) == 1
    assert docs[0] is not None


def test_svc_appset_name_follows_convention():
    """Service ApplicationSet name must be 'svcset-{slug}'."""
    rendered = render_svc_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    doc = yaml.safe_load(rendered)
    assert doc["metadata"]["name"] == f"svcset-{TENANT_SLUG}"


def test_svc_appset_git_generator_path_includes_services():
    """Service ApplicationSet git generator must reference services/* path."""
    rendered = render_svc_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    doc = yaml.safe_load(rendered)

    generators = doc["spec"]["generators"]
    git_gen = next(g for g in generators if "git" in g)
    paths = [d["path"] for d in git_gen["git"]["directories"]]
    assert any("services" in p and TENANT_SLUG in p for p in paths), (
        f"Expected services path containing tenant slug: {paths}"
    )


def test_svc_appset_has_haven_labels():
    """Both ApplicationSets must carry haven.io/managed and haven.io/tenant labels."""
    for render_fn in (render_app_appset, render_svc_appset):
        rendered = render_fn(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
        doc = yaml.safe_load(rendered)
        labels = doc["metadata"]["labels"]
        assert labels.get("haven.io/managed") == "true"
        assert labels.get("haven.io/tenant") == TENANT_SLUG


def test_app_appset_uses_multi_source():
    """App ApplicationSet must use multi-source (chart from GitHub, values from Gitea)."""
    rendered = render_app_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    doc = yaml.safe_load(rendered)
    sources = doc["spec"]["template"]["spec"]["sources"]
    assert len(sources) == 2, f"Expected 2 sources (chart + values), got {len(sources)}"
    assert sources[0]["path"] == "charts/haven-app"
    assert sources[1].get("ref") == "values"


def test_app_appset_no_gitops_prefix():
    """Generator paths must use 'tenants/{slug}/*' directly (no prefix)."""
    rendered = render_app_appset(TENANT_SLUG, chart_repo_url=REPO_URL, target_revision=REVISION)
    doc = yaml.safe_load(rendered)
    generators = doc["spec"]["generators"]
    git_gen = next(g for g in generators if "git" in g)
    paths = [d["path"] for d in git_gen["git"]["directories"]]
    assert any(p.startswith("tenants/") for p in paths), f"Expected 'tenants/' prefix: {paths}"
    assert not any(p.startswith("gitops/") for p in paths), f"gitops/ prefix should not be used: {paths}"
