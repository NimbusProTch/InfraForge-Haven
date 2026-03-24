# Keycloak Helm values (Bitnami chart)
# Sprint 1: embedded PostgreSQL. Sprint 2: migrate to CNPG cluster.
# Bitnami moved images from Docker Hub to registry.bitnami.com since 2023
global:
  imageRegistry: "registry.bitnami.com"
auth:
  adminUser: admin
  adminPassword: ${keycloak_admin_password}
postgresql:
  enabled: true
  auth:
    password: ${keycloak_db_password}
    database: keycloak
service:
  type: ClusterIP
ingress:
  enabled: false
# Production mode requires HTTPS — use edge proxy mode via gateway
production: false
proxy: edge
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    memory: "1Gi"
tolerations:
  - operator: "Exists"
