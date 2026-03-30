#!/usr/bin/env python3
"""Helper script: render and optionally commit tenant ApplicationSet YAMLs.

Renders the Jinja2 templates in this directory for a given tenant slug and
either prints the result or commits it to the haven-gitops repo via the
GitOpsService.

Usage:
    # Dry-run: print rendered YAML to stdout
    python tenant-appset-generator.py --tenant gemeente-utrecht --dry-run

    # Commit to monorepo (requires GITOPS_GITHUB_TOKEN env var)
    python tenant-appset-generator.py --tenant gemeente-utrecht --commit

    # Commit both app + service ApplicationSets for a tenant
    python tenant-appset-generator.py --tenant gemeente-utrecht --commit --both

Options:
    --tenant SLUG        Tenant slug (required)
    --repo-url URL       GitOps repo URL (default: from GITOPS_REPO_URL env)
    --revision REV       Target git revision (default: main)
    --app-chart PATH     Path to haven-app chart (default: charts/haven-app)
    --svc-chart PATH     Path to haven-managed-service chart (default: charts/haven-managed-service)
    --gitops-prefix PFX  GitOps dir prefix (default: gitops)
    --dry-run            Print rendered YAML, do not commit
    --commit             Commit rendered YAML to gitops repo
    --both               Render both app and service ApplicationSets (default: apps only)
    --output-dir DIR     Write rendered YAML to files in this directory instead of stdout
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add api/ to sys.path when running from the platform/templates directory
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root / "api") not in sys.path:
    sys.path.insert(0, str(_repo_root / "api"))

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
except ImportError:
    print("ERROR: jinja2 is not installed. Run: pip install jinja2", file=sys.stderr)
    sys.exit(1)


TEMPLATES_DIR = Path(__file__).parent
APP_TEMPLATE = "tenant-applicationset.yaml.tpl"
SVC_TEMPLATE = "service-applicationset.yaml.tpl"

DEFAULT_REPO_URL = os.getenv("GITOPS_REPO_URL", "https://github.com/NimbusProTch/InfraForge-Haven.git")
DEFAULT_REVISION = os.getenv("GITOPS_BRANCH", "main")


DEFAULT_GITOPS_REPO_URL = os.getenv(
    "GITEA_GITOPS_REPO_URL",
    "http://gitea-http.gitea-system.svc.cluster.local:3000/haven/haven-gitops.git",
)


def render_template(
    template_name: str,
    *,
    tenant_slug: str,
    gitops_repo_url: str,
    chart_repo_url: str,
    target_revision: str,
    chart_path: str,
) -> str:
    """Render a Jinja2 template and return the YAML string."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    tmpl = env.get_template(template_name)
    return tmpl.render(
        tenant_slug=tenant_slug,
        gitops_repo_url=gitops_repo_url,
        chart_repo_url=chart_repo_url,
        target_revision=target_revision,
        chart_path=chart_path,
    )


def render_app_appset(
    tenant_slug: str,
    *,
    gitops_repo_url: str = "",
    chart_repo_url: str = DEFAULT_REPO_URL,
    target_revision: str = DEFAULT_REVISION,
    chart_path: str = "charts/haven-app",
) -> str:
    """Render the tenant app ApplicationSet YAML."""
    return render_template(
        APP_TEMPLATE,
        tenant_slug=tenant_slug,
        gitops_repo_url=gitops_repo_url or DEFAULT_GITOPS_REPO_URL,
        chart_repo_url=chart_repo_url,
        target_revision=target_revision,
        chart_path=chart_path,
    )


def render_svc_appset(
    tenant_slug: str,
    *,
    gitops_repo_url: str = "",
    chart_repo_url: str = DEFAULT_REPO_URL,
    target_revision: str = DEFAULT_REVISION,
    chart_path: str = "charts/haven-managed-service",
) -> str:
    """Render the tenant service ApplicationSet YAML."""
    return render_template(
        SVC_TEMPLATE,
        tenant_slug=tenant_slug,
        gitops_repo_url=gitops_repo_url or DEFAULT_GITOPS_REPO_URL,
        chart_repo_url=chart_repo_url,
        target_revision=target_revision,
        chart_path=chart_path,
    )


async def _commit_to_gitops(
    tenant_slug: str,
    app_yaml: str | None,
    svc_yaml: str | None,
) -> None:
    """Commit rendered ApplicationSet YAMLs to the haven-gitops repo."""
    from app.services.gitops_service import GitOpsService  # type: ignore[import]

    gitops = GitOpsService()

    # ApplicationSets live outside gitops/tenants — in platform/argocd/applicationsets/
    # We write them as raw files using the underlying file write mechanism.
    async with gitops._lock:
        await gitops._ensure_repo()

        appset_dir = gitops._clone_dir / "platform" / "argocd" / "applicationsets"
        appset_dir.mkdir(parents=True, exist_ok=True)

        if app_yaml:
            path = appset_dir / f"tenant-{tenant_slug}-apps.yaml"
            path.write_text(app_yaml)
            print(f"  Written: {path}")

        if svc_yaml:
            path = appset_dir / f"tenant-{tenant_slug}-services.yaml"
            path.write_text(svc_yaml)
            print(f"  Written: {path}")

        sha = await gitops._commit_and_push(
            f"[haven] add ApplicationSets for tenant {tenant_slug}"
        )
        print(f"Committed: {sha}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render ArgoCD ApplicationSet YAMLs for a Haven tenant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--tenant", required=True, metavar="SLUG", help="Tenant slug")
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL, help="GitOps repo URL")
    parser.add_argument("--revision", default=DEFAULT_REVISION, help="Target git revision")
    parser.add_argument("--app-chart", default="charts/haven-app", help="Path to haven-app chart")
    parser.add_argument("--svc-chart", default="charts/haven-managed-service", help="Path to managed-service chart")
    # --gitops-prefix removed: Gitea repo uses tenants/{slug}/* directly (no prefix)
    parser.add_argument("--dry-run", action="store_true", help="Print rendered YAML; do not commit")
    parser.add_argument("--commit", action="store_true", help="Commit rendered YAML to gitops repo")
    parser.add_argument("--both", action="store_true", help="Render both app and service ApplicationSets")
    parser.add_argument("--output-dir", metavar="DIR", help="Write YAML files to this directory")
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    tenant_slug: str = args.tenant
    repo_url: str = args.repo_url
    revision: str = args.revision

    # Render templates
    app_yaml = render_app_appset(
        tenant_slug,
        chart_repo_url=repo_url,
        target_revision=revision,
        chart_path=args.app_chart,
    )
    svc_yaml = render_svc_appset(
        tenant_slug,
        chart_repo_url=repo_url,
        target_revision=revision,
        chart_path=args.svc_chart,
    ) if args.both else None

    if args.dry_run or (not args.commit and not args.output_dir):
        print("=== App ApplicationSet ===")
        print(app_yaml)
        if svc_yaml:
            print("\n=== Service ApplicationSet ===")
            print(svc_yaml)
        return

    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        app_file = out / f"tenant-{tenant_slug}-apps.yaml"
        app_file.write_text(app_yaml)
        print(f"Written: {app_file}")
        if svc_yaml:
            svc_file = out / f"tenant-{tenant_slug}-services.yaml"
            svc_file.write_text(svc_yaml)
            print(f"Written: {svc_file}")
        return

    if args.commit:
        asyncio.run(_commit_to_gitops(tenant_slug, app_yaml, svc_yaml))


if __name__ == "__main__":
    main()
