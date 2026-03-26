from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://haven:haven@localhost:5432/haven_platform"

    # Keycloak
    keycloak_url: str = "http://keycloak.keycloak.svc.cluster.local:8080"
    keycloak_realm: str = "haven"

    # Kubernetes
    k8s_incluster: bool = False
    k8s_kubeconfig: str | None = None

    # Harbor
    harbor_url: str = "https://harbor.example.com"
    harbor_project: str = "haven"
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

    # GitOps
    gitops_repo_url: str = ""
    gitops_branch: str = "main"
    gitops_clone_dir: str = "/tmp/haven-gitops"
    gitops_deploy_key_path: str = ""

    # ArgoCD API
    argocd_url: str = "http://argocd-server.argocd.svc.cluster.local:80"
    argocd_auth_token: str = ""

    # App
    debug: bool = False
    secret_key: str = "change-me-in-production"
    api_prefix: str = "/api/v1"


settings = Settings()
