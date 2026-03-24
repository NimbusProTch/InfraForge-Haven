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

    # App
    debug: bool = False
    api_prefix: str = "/api/v1"


settings = Settings()
