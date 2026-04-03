import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _validate_critical_settings(self) -> "Settings":
        """Warn about missing critical settings at startup."""
        missing = []
        if not self.secret_key:
            missing.append("SECRET_KEY")
        if not self.database_url:
            missing.append("DATABASE_URL")
        if missing:
            logger.warning("SECURITY WARNING: Missing critical settings: %s", ", ".join(missing))
        return self

    # Database
    database_url: str = "postgresql+asyncpg://haven:haven@localhost:5432/haven_platform"

    # Keycloak
    keycloak_url: str = "http://keycloak.keycloak.svc.cluster.local:8080"
    keycloak_realm: str = "haven"
    # Keycloak Admin API credentials (MUST be set via env var or K8s Secret)
    keycloak_admin_user: str = ""
    keycloak_admin_password: str = ""
    keycloak_admin_client_id: str = "admin-cli"

    # Kubernetes
    k8s_incluster: bool = False
    k8s_kubeconfig: str | None = None

    # Harbor
    harbor_url: str = "https://harbor.example.com"
    harbor_project: str = "haven"
    # Harbor admin password (MUST be set via env var or K8s Secret)
    harbor_admin_password: str = ""
    # Harbor registry secret name (pre-created K8s Secret with .dockerconfigjson key)
    harbor_registry_secret: str = "harbor-registry-secret"

    # Build pipeline
    build_namespace: str = "haven-builds"
    # Hetzner LB IP for sslip.io hostnames ({app}.{tenant}.apps.{lb_ip}.sslip.io)
    lb_ip: str = "127.0.0.1"

    # GitHub OAuth (for "Connect GitHub" popup flow)
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:3001/github/callback"

    # Webhook
    # GitHub webhook secret — set via WEBHOOK_SECRET env var, never hard-coded
    webhook_secret: str = ""

    # GitOps — monorepo (InfraForge-Haven), gitops/ prefix
    # Set GITOPS_REPO_URL env var to enable GitOps mode; empty = direct K8s API
    gitops_repo_url: str = ""
    gitops_branch: str = "main"
    gitops_clone_dir: str = "/tmp/haven-gitops"
    gitops_deploy_key_path: str = ""
    # GitHub PAT for pushing to the monorepo (set via GITOPS_GITHUB_TOKEN in secrets)
    gitops_github_token: str = ""

    # ArgoCD API
    argocd_url: str = "http://argocd-server.argocd.svc.cluster.local:80"
    argocd_auth_token: str = ""

    # Redis (git queue, session cache)
    redis_url: str = "redis://localhost:6379/0"

    # Gitea self-hosted git server
    # Set GITEA_URL to the in-cluster service URL (e.g. http://gitea-http.gitea-system.svc.cluster.local:3000)
    gitea_url: str = ""
    gitea_admin_token: str = ""
    # Gitea org and repo for GitOps manifests
    gitea_org: str = "haven"
    gitea_gitops_repo: str = "haven-gitops"
    gitea_gitops_branch: str = "main"

    # Percona Everest (DB provisioning for PostgreSQL, MySQL, MongoDB)
    everest_url: str = "http://everest.everest-system.svc.cluster.local:8080"
    # Everest admin credentials (MUST be set via env var or K8s Secret)
    everest_admin_user: str = ""
    everest_admin_password: str = ""
    everest_namespace: str = "everest"

    # CORS allowed origins (comma-separated list)
    cors_origins: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://127.0.0.1:3000,http://127.0.0.1:3001"
    )

    # App
    debug: bool = False
    secret_key: str = ""  # MUST be set via env var (used for JWT signing)
    api_prefix: str = "/api/v1"

    # ArgoCD ApplicationSet — cluster-internal Gitea URL (ArgoCD runs inside cluster)
    # If empty, falls back to gitops_repo_url (which may be localhost for local dev)
    gitops_argocd_repo_url: str = ""

    # Helm chart repo URL for ArgoCD multi-source (default: InfraForge-Haven GitHub)
    chart_repo_url: str = ""

    # HashiCorp Vault (sensitive env var storage)
    # Set VAULT_URL + VAULT_TOKEN to enable Vault; empty = direct K8s Secrets fallback
    vault_url: str = ""
    vault_token: str = ""


settings = Settings()
