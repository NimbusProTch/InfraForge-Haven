---
paths:
  - "api/**"
  - "infrastructure/**"
  - "platform/**"
  - ".github/**"
---

# Güvenlik Kuralları

## Credentials
- Secret'ları ASLA koda yazma — tfvars, .env, K8s Secret kullan
- Token/password conversation'da paylaşılırsa HEMEN rotate uyarısı ver
- .gitignore kontrol et: terraform.tfvars, .env, kubeconfig, *.pem, *.key

## API Güvenliği
- Her endpoint'te auth dependency zorunlu (TenantMembership veya CurrentUser)
- Cross-tenant data leakage: SQL query'lerde tenant_id filter zorunlu
- Rate limiting: hassas endpoint'lerde per-endpoint limit
- Input validation: Pydantic BaseModel zorunlu
- CORS: wildcard (*) YASAK

## K8s / Infra
- PSA restricted profile: tenant namespace'lerde zorunlu
- BuildKit: rootless image + securityContext (runAsNonRoot, drop ALL)
- operator_cidrs: 0.0.0.0/0 YASAK, validation ile engelle
- Kyverno: tenant namespace'lerde policy enforcement
- Firewall: gereksiz port açma

## CI/CD
- Workflow'larda secret'lar ${{ secrets.* }} ile
- SARIF upload: continue-on-error: true (permission sorunları için)
- Docker image tag: digest pin (@sha256:) tercih et
