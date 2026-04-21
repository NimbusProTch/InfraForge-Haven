# Bölge 2.V — Secret Inventory Audit (2026-04-21)

Faz 2.V (Vault Integration) migration PR'larının **input** belgesi. Her K8s Secret field'ı için: bugünkü durum → hedef Vault path + ESO CRD → rotation politikası → migration PR atıf. Sonraki session'larda bu tabloyu kırmızıdan yeşile çeviriyoruz.

**Cluster**: `infrastructure/environments/prod/kubeconfig`  
**Vault endpoint**: `http://vault.vault-system.svc.cluster.local:8200` (TLS disabled, ingress yok)  
**Vault auth method**: **henüz karar vermedik** (JWT/Kubernetes SA / Token). 2.V.2 ilk aday: `kubernetes` auth method + SA token review.

## Renk kodu

- 🔴 **P0**: dev default / literal placeholder / zayıf değer — önce rotate, sonra Vault
- 🟠 **P1**: gerçek değer ama plaintext K8s Secret'ta — Vault'a taşı
- 🟢 **OK**: public veya zaten güçlü + Vault-bound
- ⚪ **N/A**: TLS cert, script, derived metadata

## 1. `haven-system/iyziops-api-secrets` (9 field)

| Field | Uzunluk | Severity | Şu an | Hedef Vault path | Rotation | PR |
|---|---|---|---|---|---|---|
| DATABASE_URL | 118 | 🟠 | plaintext | `kv/platform/iyziops-api/database` | 90 gün + CNPG rotate | 2.V.3 |
| EVEREST_ADMIN_PASSWORD | 64 | 🟠 | plaintext | `kv/platform/everest/admin` | 180 gün | 2.V.4 |
| GITEA_ADMIN_TOKEN | 40 | 🟠 | plaintext | `kv/platform/gitea/admin-token` | 90 gün | 2.V.7 |
| GITHUB_CLIENT_ID | 20 | 🟢 | public (OAuth App ID) | → ConfigMap (Vault gerekmez) | — | 2.V.3 ile |
| GITHUB_CLIENT_SECRET | 40 | 🟠 | plaintext **gerçek** değer | `kv/platform/iyziops-api/github-repo-oauth` | 90 gün (manual GitHub regen) | 2.V.3 ile |
| HARBOR_ADMIN_PASSWORD | 11 | 🔴 | `Harbor12345` dev default | `kv/platform/harbor/admin` | **önce rotate**, sonra Vault | 2.V.6 |
| KEYCLOAK_ADMIN_PASSWORD | 15 | 🔴 | `dev-placeholder` **uyumsuz** | `kv/platform/keycloak/admin` | **Deployment env uyuşmazlığı çöz** önce | 2.V.5 |
| SECRET_KEY | 52 | 🔴 | `overnight-dev-key-do-not-use-…` | `kv/platform/iyziops-api/session-secret` | **rotate + 180 gün** | 2.V.3 ile |
| WEBHOOK_SECRET | 11 | 🔴 | `placeholder` literal | `kv/platform/iyziops-api/webhook-secret` | **rotate zorunlu — webhook sig doğrulanmıyor** | 2.V.3 ile |

### Risk notları

1. `WEBHOOK_SECRET='placeholder'` demek **webhook signature check anlamsız**. Herhangi bir saldırgan `POST /webhooks/gitea/{token}` veya `POST /webhooks/github/{token}` canlı imza geçirir. **P0 incident** sayılabilir — bu sprintte ilk düzeltilmesi gereken değer.
2. `SECRET_KEY` FastAPI SessionMiddleware / JWT decode kullanıyor olabilir; rotate → mevcut tüm oturumlar invalid. Rollout window seç.
3. `KEYCLOAK_ADMIN_PASSWORD='dev-placeholder'` ama Keycloak Deployment env'de `KC_BOOTSTRAP_ADMIN_PASSWORD='keycloak-admin-dev-2026'` — iki değer farklı. Backend Keycloak'u hangi değerle çağırıyor? Test sonrası `dev-placeholder` dead string bile olabilir.

## 2. `haven-system/iyziops-ui-secrets` (8 field)

| Field | Uzunluk | Severity | Şu an | Hedef | Rotation | PR |
|---|---|---|---|---|---|---|
| GITHUB_ID | 11 | 🔴 | `placeholder` literal | `kv/platform/iyziops-ui/github-signin` | **önce OAuth App** kaydet | 2.V.10 (yeni) |
| GITHUB_SECRET | 11 | 🔴 | `placeholder` literal | aynı | aynı | 2.V.10 |
| KEYCLOAK_CLIENT_ID | 8 | 🟢 | `haven-ui` public | → ConfigMap | — | 2.V.5 ile |
| KEYCLOAK_CLIENT_SECRET | 24 | 🔴 | `haven-ui-dev-secret-2026` dev default | `kv/platform/keycloak/iyziops-ui-client` | **rotate Keycloak client + Vault** | 2.V.5 |
| KEYCLOAK_ID | 8 | 🟢 | `haven-ui` (duplicate) | ConfigMap | — | 2.V.5 ile |
| KEYCLOAK_SECRET | 24 | 🔴 | duplicate (`haven-ui-dev-secret-2026`) | aynı | aynı | 2.V.5 |
| NEXTAUTH_SECRET | 59 | 🔴 | `overnight-dev-nextauth-secret-do-not-use…` | `kv/platform/iyziops-ui/nextauth` | **rotate** | 2.V.10 |
| NEXTAUTH_URL | 19 | 🟢 | `https://iyziops.com` | ConfigMap | — | 2.V.10 ile |

### Keşif

UI'da **NextAuth GitHub provider** için ayrı OAuth App gerekiyor (API'daki repo OAuth App'i farklı amaç). Plan'da 2.0.5'te Keycloak GitHub IdP'yi eklemeyi konuşmuştuk. **Daha temiz yaklaşım**: UI GitHub provider'ı **Keycloak IdP üzerinden** çalışsın — UI hiç GitHub OAuth yapmasın, sadece Keycloak'a konuşsun; Keycloak'ta GitHub IdP broker olsun. O zaman UI'daki `GITHUB_ID/SECRET` silinebilir. Daha sade.

Plan kararı (PR 2.0.5 güncellemesi): UI NextAuth GitHub provider'ı **kaldır** (UI sadece Keycloak provider kullansın); Keycloak realm'e GitHub IdP ekle; UI sign-in sayfasındaki "Sign in with GitHub" butonu `kc_idp_hint=github` parametreli Keycloak login URL'ine yönlendirsin. Böylece **bir tek OAuth App** kayıt yeter (Keycloak'ın).

**Yeni PR**: 2.V.10 UI NextAuth sekundaryLeri rotate et (UI GitHub provider kaldırıldıktan sonra yalnız NEXTAUTH_SECRET + ConfigMap kalıyor).

## 3. `keycloak/` (Deployment env — K8s Secret BİLE DEĞİL)

Tüm Keycloak admin + DB env'leri Deployment'ta plaintext env var:

| Env | Severity | Şu an | Hedef | PR |
|---|---|---|---|---|
| KC_BOOTSTRAP_ADMIN_USERNAME | 🟢 | `admin` | ConfigMap | 2.V.5 |
| KC_BOOTSTRAP_ADMIN_PASSWORD | 🔴 | `keycloak-admin-dev-2026` | ExternalSecret → `keycloak-admin-credentials` Secret | 2.V.5 |
| KC_DB_URL | 🟢 | `jdbc:postgresql://…` public | ConfigMap | 2.V.5 |
| KC_DB_USERNAME | 🟢 | `haven` | ConfigMap | 2.V.5 |
| KC_DB_PASSWORD | 🔴 | `haven-platform-db-2026` | ExternalSecret → `keycloak-db-credentials` | 2.V.5 |

**PR 2.V.5 kapsamı**: Keycloak Deployment spec refactor — tüm env'leri Vault-sourced ExternalSecret'larla K8s Secret'a almak + Deployment spec'i `env.valueFrom.secretKeyRef`'e geçirmek. **Risk**: Deployment rollout yanlış sırada Keycloak DB ile bağlantıyı keserse realm kaybı. Rollout sırası:
1. ExternalSecret yarat + K8s Secret ready
2. Keycloak Deployment spec patch (env → envFrom/valueFrom)
3. Rollout restart + health check
4. `kcadm get realms/haven` smoke

## 4. `harbor-system/harbor-core` (8 field)

| Field | Uzunluk | Severity | Hedef | PR |
|---|---|---|---|---|
| CSRF_KEY | 32 | 🟠 | `kv/platform/harbor/csrf` | 2.V.6 |
| HARBOR_ADMIN_PASSWORD | 11 | 🔴 (Harbor12345) | `kv/platform/harbor/admin` (rotate+Vault) | 2.V.6 |
| POSTGRESQL_PASSWORD | 8 | 🔴 (**zayıf**) | `kv/platform/harbor/db` | 2.V.6 |
| REGISTRY_CREDENTIAL_PASSWORD | 24 | 🟠 | `kv/platform/harbor/registry-cred` | 2.V.6 |
| secret | 16 | 🟠 | `kv/platform/harbor/internal-secret` | 2.V.6 |
| secretKey | 16 | 🟠 | `kv/platform/harbor/internal-secretkey` | 2.V.6 |
| tls.crt | — | ⚪ | (cert-manager managed) | — |
| tls.key | — | ⚪ | — | — |

**Risk**: Harbor Helm chart stock secret'ları; Vault'a taşırken Helm release'in "value overwrite" davranışı test edilmeli. ArgoCD `IgnoreDifferences` + ESO reconcile döngüsü gerekebilir.

## 5. `minio-system/minio-credentials` (2 field)

| Field | Uzunluk | Severity | Hedef | PR |
|---|---|---|---|---|
| rootUser | 19 | 🟢 | `kv/platform/minio/root-user` | 2.V.8 |
| rootPassword | 40 | 🟢 (**strong**, OK değer) | `kv/platform/minio/root-password` | 2.V.8 |

MinIO root credentials güçlü; rotate opsiyonel, Vault'a taşıma zorunlu.

## 6. `gitea-system/gitea-*` (script secrets — credential değil)

`gitea-init` Secret'ı init script'leri tutuyor. Gitea admin user (`haven-admin`) credential'ı Gitea Deployment env'inde olmalı; `gitea-inline-config` ConfigMap'ı da kontrol edilecek (13 data field). **Follow-up audit**: PR 2.V.7'den önce `kubectl -n gitea-system get deployment gitea -o yaml | grep -A2 env` → `GITEA_ADMIN_*` env'leri nerede saklandığını tespit et.

## 7. Kullanılmayan / Meta Secret'lar

- `haven-system/haven-platform-ca` — CNPG CA (CNPG-managed, ESO dışında)
- `haven-system/haven-platform-replication` — CNPG TLS (CNPG-managed)
- `haven-system/haven-platform-server` — CNPG TLS (CNPG-managed)
- `haven-system/haven-platform-db-creds` — CNPG superuser (CNPG-managed, **ama** backend buradan DATABASE_URL türetiyorsa audit)
- `haven-system/iyziops-argocd-token` — ArgoCD sync token (rotate + Vault adayı, 2.V.9)

## 8. Migration sırası (revize edilmiş)

Baseline audit bulgularından sonra plan'daki 2.V.x sırası şöyle güncelleniyor:

| Sıra | PR | İş | Prereq |
|---|---|---|---|
| 1 | 2.V.WEBHOOK | **WEBHOOK_SECRET rotate** — acil güvenlik fix, hardcoded `placeholder` webhook signature'ı açık | yok |
| 2 | 2.V.2 | ClusterSecretStore `vault-backend` kur + kubernetes auth method | yok |
| 3 | 2.V.3 | iyziops-api API secrets (DATABASE_URL, GITHUB_*, SECRET_KEY, WEBHOOK_SECRET) Vault'a | #2 |
| 4 | 2.V.5 | Keycloak Deployment refactor + admin/DB password Vault'a | #2 + rotate |
| 5 | 2.V.6 | Harbor secrets Vault'a + Harbor12345 rotate | #2 + rotate |
| 6 | 2.V.7 | Gitea admin token Vault'a | #2 |
| 7 | 2.V.8 | MinIO root Vault'a | #2 |
| 8 | 2.V.10 | UI NextAuth + Keycloak client secrets Vault'a (UI GitHub provider kaldırıldıktan sonra) | #2 + 2.0.5 |
| 9 | 2.V.4 | Everest admin password Vault'a | #2 |
| 10 | 2.V.9 | iyziops-argocd-token Vault'a | #2 |
| 11 | 2.V.1 | **Vault auto-unseal** — bu en büyük iş, en sona; şimdiye kadar Vault çökmezse acil değil | — |
| 12 | 2.V.Rotation | Rotation runbook + canlı rotate test | tüm yukarıdakiler |

Rationale for Vault auto-unseal deprioritization:
- Vault 4d6h uptime, sıfır restart
- Restart olursa manual unseal var (memory'de credential)
- Auto-unseal için Hetzner'da kolay KMS yok; Transit self-unseal ayrı bir Vault gerektirir — büyük iş
- Önce data migration, sonra operational hardening

**Interim runbook requirement** (architect review gereği): Vault pod'u bir sebepten yeniden
başlarsa (node drain, kernel patch, OOM kill) cluster 3am'de sealed kalır ve tüm ExternalSecret
reconciliation durur. On-call prosedürü:

1. `kubectl --kubeconfig=$KC -n vault-system exec vault-0 -- vault status` → sealed teyit
2. Unseal key: `memory/vault_credentials_20260417.md` (1-of-1 Shamir)
3. `kubectl --kubeconfig=$KC -n vault-system exec vault-0 -- vault operator unseal <key>`
4. ESO'nun yeniden connect olduğunu doğrula: `kubectl get externalsecret -A` → SecretSynced True

Faz 2.V.1 tamamlanınca bu manual adım kaybolur.

## 9. Secret naming convention (bundan sonraki her şey için)

- **Vault KV v2 logical path**: `platform/<service>/<purpose>` — ESO `vault` provider `/data/`'ı kendisi ekler, elle yazma
- **Vault API REST path** (kcli / curl için): `v1/kv/data/platform/<service>/<purpose>` — ESO değil, manuel test için
- ExternalSecret name: `<target-secret-name>-vault`
- Target K8s Secret name: mevcut adı koru (Deployment `envFrom` değişmesin)
- Refresh interval: 1h
- `creationPolicy: Owner` — Secret tamamen ESO-yönetimli (Merge deprecated v0.9+)

Örnek (2.V.3 için):
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: iyziops-api-secrets-vault
  namespace: haven-system
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: iyziops-api-secrets
    creationPolicy: Owner  # ESO fully manages; Merge deprecated since v0.9
  data:
    - secretKey: DATABASE_URL
      remoteRef:
        key: platform/iyziops-api/database  # logical path — ESO inserts /data/
        property: url
    - secretKey: GITHUB_CLIENT_SECRET
      remoteRef:
        key: platform/iyziops-api/github-repo-oauth
        property: client_secret
    ...
```

## 10. Referanslar

- Baseline audit: `docs/audits/bolge-2-baseline-2026-04-21.md`
- Memory: `memory/vault_credentials_20260417.md` (unseal key + root token; rotate-asap)
- Plan: `/Users/gaskin/.claude/plans/yeni-session-ba-latt-nda-binary-anchor.md` Faz 2.V bölümü
- Scratch logs: `logs/scratch-secrets-inventory-*.log`, `logs/scratch-ui-harbor-gitea-minio-secrets-*.log`
