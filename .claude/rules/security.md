---
paths:
  - "api/**"
  - "infrastructure/**"
  - "platform/**"
  - ".github/**"
---

# Security Rules

## Credentials
- NEVER hardcode secrets — use tfvars, .env, K8s Secrets
- If token/password appears in conversation: IMMEDIATELY warn to rotate
- Verify .gitignore: terraform.tfvars, .env, kubeconfig, *.pem, *.key

## API Security
- Every endpoint requires auth dependency (TenantMembership or CurrentUser)
- Cross-tenant data leakage: SQL queries MUST filter by tenant_id
- Rate limiting on sensitive endpoints
- Input validation: Pydantic BaseModel mandatory
- CORS: wildcard (*) FORBIDDEN

## K8s / Infrastructure
- PSA restricted profile on all tenant namespaces
- BuildKit: rootless image + securityContext (runAsNonRoot, drop ALL)
- operator_cidrs: 0.0.0.0/0 FORBIDDEN, enforce via validation
- Kyverno: policy enforcement on tenant namespaces
- Do not open unnecessary firewall ports

## CI/CD
- Secrets via `${{ secrets.* }}` only
- SARIF upload: add continue-on-error for permission issues
- Prefer image digest pin (@sha256:) over tags
