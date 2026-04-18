"""Static contract test: permanent demo app files exist with expected shape.

Ensures `demo/` dir remains intact and follows the contract iyziops UI expects.
If someone accidentally deletes demo/ or breaks the deploy contract (removes
health endpoint, renames env vars, etc.), CI catches it before merge.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO = REPO_ROOT / "demo"


def test_demo_directory_structure():
    assert DEMO.is_dir(), "demo/ removed — the permanent demo MUST stay in repo root"
    for path in [
        "api/app.py",
        "api/Dockerfile",
        "api/requirements.txt",
        "api/README.md",
        "ui/app/page.tsx",
        "ui/app/layout.tsx",
        "ui/app/providers.tsx",
        "ui/lib/api.ts",
        "ui/Dockerfile",
        "ui/package.json",
        "ui/next.config.js",
        "README.md",
        "docker-compose.yml",
    ]:
        assert (DEMO / path).is_file(), f"demo/{path} missing"


def test_demo_api_uses_all_three_services():
    """demo/api must consume DATABASE_URL, REDIS_URL, RABBITMQ_URL."""
    src = (DEMO / "api" / "app.py").read_text()
    assert "DATABASE_URL" in src, "demo-api must read DATABASE_URL (Everest injects this)"
    assert "REDIS_URL" in src, "demo-api must read REDIS_URL (Redis operator injects this)"
    assert "RABBITMQ_URL" in src, "demo-api must read RABBITMQ_URL (RabbitMQ op injects this)"
    for ep in ["/health", "/ready", "/test", "/stats", "/notes"]:
        assert ep in src, f"demo-api must expose {ep}"


def test_demo_api_cors_is_literal_origins():
    """Platform rule: CORS wildcard FORBIDDEN. Must be comma-separated origins."""
    src = (DEMO / "api" / "app.py").read_text()
    assert "CORSMiddleware" in src
    # The default must be literal origins, not "*"
    assert "allow_origins" in src
    # No wildcard in default
    assert 'allow_origins=["*"]' not in src, "CORS wildcard FORBIDDEN per security.md"


def test_demo_api_dockerfile_non_root():
    """PSA restricted: demo-api container must NOT run as root."""
    src = (DEMO / "api" / "Dockerfile").read_text()
    assert "USER 10001" in src or "USER app" in src, "demo-api Dockerfile must declare non-root USER"


def test_demo_ui_uses_api_url_env():
    """demo-ui reads NEXT_PUBLIC_API_URL at build time."""
    api_ts = (DEMO / "ui" / "lib" / "api.ts").read_text()
    assert "NEXT_PUBLIC_API_URL" in api_ts, "demo-ui api.ts must reference NEXT_PUBLIC_API_URL"
    dockerfile = (DEMO / "ui" / "Dockerfile").read_text()
    assert "ARG NEXT_PUBLIC_API_URL" in dockerfile, "demo-ui Dockerfile must ARG NEXT_PUBLIC_API_URL (build-time)"


def test_demo_ui_dockerfile_non_root():
    src = (DEMO / "ui" / "Dockerfile").read_text()
    assert "USER 10001" in src or "USER app" in src


def test_demo_readme_has_ui_deploy_steps():
    """README must document UI-driven deploy (customer pitch)."""
    src = (DEMO / "README.md").read_text()
    assert "New App" in src, "README must reference the 'New App' wizard step"
    assert "demo-api.iyziops.com" in src
    assert "demo.iyziops.com" in src
    assert "Services tab" in src or "services tab" in src.lower(), "README must describe creating services via UI"
