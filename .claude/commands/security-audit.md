# /security-audit — Full Security Audit

Haven platformunun kapsamlı güvenlik taraması. Multi-agent ile paralel çalış.

## Zorunlu Akış

3 Explore agent paralel başlat:

### Agent 1: Authentication & Authorization
- JWT doğrulama (issuer, audience, expiry, algorithm)
- Token revocation mekanizması
- RBAC implementasyonu (rol hierarchy, tenant scoping)
- Auth dependency coverage (korumasız endpoint var mı?)
- OAuth flow güvenliği (CSRF, state validation)
- Keycloak konfigürasyonu

### Agent 2: Data Isolation & Network
- Cross-tenant data leakage (SQL query filtering)
- CiliumNetworkPolicy etkinliği
- Secret management (hardcoded credentials, .gitignore)
- Harbor/Gitea/Everest izolasyonu
- Build pipeline güvenliği (container escape, privilege escalation)
- Namespace isolation completeness

### Agent 3: Infrastructure & API
- CORS konfigürasyonu
- Rate limiting
- Input validation (Pydantic, SQL injection)
- SSRF riski
- Error message information leakage
- Helm chart versioning
- TLS/certificate management
- Firewall rules
- Pod security contexts

## Rapor Formatı

Her bulgu için:

| # | Severity | Category | Finding | File:Line | Status | Recommendation |
|---|----------|----------|---------|-----------|--------|---------------|

Severity levels: CRITICAL / HIGH / MEDIUM / LOW / INFO

## KURALLAR
- Her bulgu gerçek dosya yolu ve satır numarası ile desteklenmeli
- "Sorun yok" demek yeterli değil — neden yok, hangi mekanizma koruyor?
- Daha önce fixlenmiş bulgular için: fix doğru mu, bypass edilebilir mi?
- OWASP Top 10 perspektifinden değerlendir
