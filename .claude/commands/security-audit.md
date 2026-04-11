# /security-audit — Full Security Audit

Comprehensive security scan of the Haven platform. Run multi-agent in parallel.

## Mandatory Flow — Launch 3 Explore agents:

### Agent 1: Authentication & Authorization
- JWT verification (issuer, audience, expiry, algorithm)
- Token revocation mechanism
- RBAC implementation (role hierarchy, tenant scoping)
- Auth dependency coverage (any unprotected endpoints?)
- OAuth flow security (CSRF, state validation)

### Agent 2: Data Isolation & Network
- Cross-tenant data leakage (SQL query filtering)
- CiliumNetworkPolicy effectiveness
- Secret management (hardcoded credentials, .gitignore)
- Build pipeline security (container escape, privilege escalation)
- Namespace isolation completeness

### Agent 3: Infrastructure & API
- CORS configuration
- Rate limiting
- Input validation (Pydantic, SQL injection)
- SSRF risk
- Error message information leakage
- Helm chart versioning, TLS, firewall rules

## Report Format
| # | Severity | Category | Finding | File:Line | Status | Fix |
|---|----------|----------|---------|-----------|--------|-----|

Severity: CRITICAL / HIGH / MEDIUM / LOW / INFO
