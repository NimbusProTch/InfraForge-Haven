# Bölge 2 Baseline Audit — 2026-04-21

Sprint açılışı canlı cluster fotoğrafı. Plan dosyası `/Users/gaskin/.claude/plans/yeni-session-ba-latt-nda-binary-anchor.md`. Bu belge Faz 2.0 / 2.V / 2.A işlerinin **önceki durumunu** sabitliyor — her PR'ın ardından güncelleme geldikçe farklar buraya değil, PR açıklamalarına yazılır.

Kubeconfig: `infrastructure/environments/prod/kubeconfig` (yerel fetch, 2 gün önce).

## 1. Node & Control Plane

```
NAME               STATUS   ROLES                       AGE    VERSION
iyziops-master-0   Ready    control-plane,etcd,master   6d13h  v1.32.3+rke2r1
iyziops-master-1   Ready    control-plane,etcd,master   6d13h  v1.32.3+rke2r1
iyziops-master-2   Ready    control-plane,etcd,master   3d9h   v1.32.3+rke2r1
iyziops-worker-0   Ready    <none>                      6d13h  v1.32.3+rke2r1
iyziops-worker-1   Ready    <none>                      6d13h  v1.32.3+rke2r1
iyziops-worker-2   Ready    <none>                      6d13h  v1.32.3+rke2r1
```

RKE2 1.32.3 + containerd 2.0.4, 3×3 topoloji, healthy.

## 2. Namespace envanteri

`argocd, cert-manager, cilium-secrets, cnpg-system, default, everest, everest-monitoring, everest-olm, everest-system, external-secrets, gitea-system, harbor-system, haven-builds, haven-system, iyziops-gateway, kafka-system, keycloak, kube-node-lease, kube-public, kube-system, kyverno-system, logging, longhorn-system, minio-system, monitoring, rabbitmq-system, redis-system, temp-registry, tenant-demo, tenant-test, vault-system`

Kritik isim haritası (ArgoCD app adı → ns):
- `vault` → **vault-system** (unutma: plan'da "vault" ns olarak yazılmıştı; gerçek isim farklı)
- `keycloak` → **keycloak** ns
- `iyziops-api` + `iyziops-ui` + `haven-platform` (CNPG) → **haven-system**

## 3. ArgoCD Applications

20+ app, hepsi Synced. **Degraded**: `harbor` (1.16.2 — `harbor-registry-*` pod 5h+ ContainerCreating stuck, kaynak veya PVC sorunu olabilir). Geri kalan hepsi Healthy.

`appset-demo` (2d10h) + `appset-test` (43h) hâlâ duruyor — L11 cleanup açık.

## 4. Public Endpoint Smoke

| URL | HTTP | Süre |
|---|---|---|
| https://iyziops.com/ | 200 | 0.41s |
| https://api.iyziops.com/api/docs | 200 | 0.30s |
| https://api.iyziops.com/api/openapi.json | 200 | 0.71s |
| https://keycloak.iyziops.com/health/ready | **404** | 0.29s |
| https://demo.iyziops.com/ | 200 | 0.22s |
| https://demo-api.iyziops.com/ | 200 | 0.22s |

`/health/ready` 404: Keycloak probe path yanlış ya da HTTPRoute trim yapıyor. Aşağıda follow-up.

## 5. Vault (vault-system/vault-0)

```
Sealed:         false
Initialized:    true
Seal Type:      shamir (1-of-1)
Storage:        file (local /vault/data)
HA Enabled:     false
Version:        1.18.2
Build Date:     2024-11-20
```

Config (`vault-config` CM):
```
ui = true
listener "tcp" { tls_disable = 1 ... }
storage "file" { path = "/vault/data" }
disable_mlock = true
```

### Bulgular

- **Auto-unseal YOK**: Seal type shamir. Pod restart → sealed. `seal "transit"` / `seal "awskms"` / `seal "gcpkms"` tanımlı değil. Memory `vault_credentials_20260417.md` unseal key + root token yaşıyor.
- **vault-system ns'de hiç Secret yok** — Vault root token / unseal keys K8s Secret olarak yok; operatör lokalinde.
- **File storage** (HA yok) — prod için yeterli değil ama şimdilik feature'a engel değil.
- **TLS disabled on listener** — mTLS yok, ingress-side TLS (cert-manager) olmadığı sürece internal cluster'da plaintext. HTTPRoute da bulunmadı (`kubectl get httproute -A`).

### Faz 2.V impact

2.V.1 auto-unseal işi gerçek bir iş: transit veya AWS/GCP KMS gerekiyor. Kısa yol: ikinci bir small Vault transit-unseal için. Uzun yol: Hetzner Object Storage'da KMS yok, Transit tek seçenek.

## 6. ESO (external-secrets-operator)

Operator ayakta, altyapı hazır ama **hiçbir migration yapılmamış**:

```
external-secrets-867bb658c5-zbxmp                   1/1 Running   4 restarts   6d13h
external-secrets-cert-controller-5f8b86f8fd-fl8b6   1/1 Running   0            6d13h
external-secrets-webhook-6b94cd54b6-kvkvl           1/1 Running   0            6d13h
```

CRD'ler: acraccesstokens, clusterexternalsecrets, clustersecretstores, ecrauthorizationtokens, externalsecrets, fakes, gcraccesstokens, githubaccesstokens, passwords, pushsecrets, secretstores, stssessiontokens, uuids, vaultdynamicsecrets, webhooks (hepsi 6d13h önce kuruldu).

```
ClusterSecretStore: No resources found
ExternalSecret: No resources found
```

**Durum**: Operator 6 gündür çalışıyor, bir tek Vault'a bağlı `ClusterSecretStore` yok. PR #117 "plan drafted, #118 relocate hot fix" sonrası çalışmayı tamamen kesmişiz. 2.V.2'nin hedefi: en az bir `ClusterSecretStore vault-backend` canlı + state Ready.

4 restart Operator pod'ında — nedenini bulmak zorunlu değil ama not: `kubectl -n external-secrets logs deploy/external-secrets --previous`.

## 7. iyziops-api-secrets inventory (haven-system)

9 field, hepsi plaintext K8s Secret:

| Field | Uzunluk | Değer Preview | Sınıf |
|---|---|---|---|
| DATABASE_URL | 118 | `postgresql+asyncpg://haven:hav…` | 🔒 Vault'a |
| EVEREST_ADMIN_PASSWORD | 64 | `h9SAlzxDtj66biJfgFgjbBwSMDNfeE…` | 🔒 Vault'a |
| GITEA_ADMIN_TOKEN | 40 | `2b2c8945222a4820cfdd1852e6823a…` | 🔒 Vault'a |
| **GITHUB_CLIENT_ID** | 20 | `Ov23liUCbuiXlKzAgdmZ` | 📄 public (konfigmap'e) |
| **GITHUB_CLIENT_SECRET** | 40 | `0a4d86f14cdc3b286f694eb6fc813f…` | 🔒 Vault'a — **GERÇEK DEĞER** |
| HARBOR_ADMIN_PASSWORD | 11 | `Harbor12345` | 🔒 Vault'a **+ rotate** (dev default) |
| KEYCLOAK_ADMIN_PASSWORD | 15 | `dev-placeholder` | 🔒 **Deploy env vs secret uyuşmazlığı** (aşağı bak) |
| SECRET_KEY | 52 | `overnight-dev-key-do-not-use-i…` | 🔒 **rotate zorunlu** |
| WEBHOOK_SECRET | 11 | `placeholder` | 🔒 **literal placeholder, rotate zorunlu** |

### Kritik

1. **GITHUB placeholder bug RESOLVED**: `memory/project_github_oauth_placeholder_bug.md`'da açık olarak duran bug aslında **patch'lenmiş** — real client_id/secret `iyziops-api-secrets`'ta. Memory güncellenecek.
2. **WEBHOOK_SECRET = `placeholder`**: Gitea/GitHub webhook signature doğrulaması anlamsız — herhangi bir push event kabul edilir. Rotate + Vault.
3. **SECRET_KEY = `overnight-dev-key-do-not-use-i…`**: FastAPI/SQLAlchemy session secret dev değeri. Her restart'ta oturumlar geçersiz kalmalı — rotate.
4. **Harbor12345**: rotate + Vault.
5. **Uyuşmazlık**: Keycloak Deployment env'de `KC_BOOTSTRAP_ADMIN_PASSWORD='keycloak-admin-dev-2026'` plaintext. Ama iyziops-api-secrets'taki `KEYCLOAK_ADMIN_PASSWORD='dev-placeholder'` — iki değer farklı. iyziops-api hangisini kullanıyor? (backend Keycloak admin çağrıları ya 401 ya başka mekanizma; audit follow-up).

### Diğer haven-system secret'lar

```
haven-platform-ca              Opaque      2      3d20h (CNPG CA)
haven-platform-db-creds        basic-auth  2      3d20h (CNPG superuser)
haven-platform-replication     kubernetes.io/tls 2  3d20h
haven-platform-server          kubernetes.io/tls 2  3d20h
iyziops-argocd-token           Opaque      1      2d10h (ArgoCD sync token for API)
iyziops-ui-secrets             Opaque      8      4d5h (UI env)
```

iyziops-ui-secrets 8 field — muhtemelen `NEXT_PUBLIC_API_URL`, `KEYCLOAK_*` client config; detay Faz 2.V'de.

## 8. Keycloak (keycloak/keycloak-*)

```
NAME                        READY   STATUS    RESTARTS   AGE
keycloak-6869ff965c-4tktj   1/1     Running   0          3d20h
```

Deployment env'de plaintext credentials:

| Env | Değer |
|---|---|
| KC_BOOTSTRAP_ADMIN_USERNAME | `admin` |
| **KC_BOOTSTRAP_ADMIN_PASSWORD** | **`keycloak-admin-dev-2026`** 🔒 (**PLAINTEXT ENV, Vault'a zorunlu**) |
| KC_DB | `postgres` |
| KC_DB_URL | `jdbc:postgresql://haven-platform-rw.haven-system.svc.cluster.local:5432/keycloak` |
| KC_DB_USERNAME | `haven` |
| **KC_DB_PASSWORD** | **`haven-platform-db-2026`** 🔒 (**PLAINTEXT ENV, Vault'a zorunlu**) |
| KC_PROXY_HEADERS | `xforwarded` |
| KC_HOSTNAME_STRICT | `false` |

### Bulgular

- **İki plaintext password deploy env'de** — K8s Secret bile değil.
- **SMTP env'de yok** — realm-level config olmalı. `kcadm get realms/haven` ile doğrula (2.0.4 Forgot Password prereq).
- **GitHub IdP env'de yok** — realm-level. Realm JSON görülmeli (2.0.5 Sign in with GitHub prereq).
- **keycloak ns'de hiç Secret yok** — Faz 2.V migration'da `keycloak-admin-credentials` + `keycloak-db-credentials` Vault-sourced ExternalSecret'larla yaratılacak, Deployment env `valueFrom.secretKeyRef`'e dönüşecek.

## 9. Tenants & ArgoCD AppSets

| ns | age | kaynak durum |
|---|---|---|
| tenant-demo | 2d10h | ArgoCD `demo-demo-api` + `demo-demo-ui` Synced/Healthy; **7× `app-pg-1-initdb` Error pod 36h+** |
| tenant-test | 43h | ArgoCD `test-test` Synced/Healthy |

AppSet'ler:
- appset-demo (2d10h)
- appset-test (43h)

L11 memory notu: "Scrap sprint-demo, rebuild via UI end-to-end". Faz 2.A audit test'i için yeni `bootstrap-audit-2026-04-21` tenant'ı yaratılacak; eskisine dokunulmayacak (demo app canlı).

## 10. Haven System Pod Health

```
haven-platform-1               1/1 Running   3d20h  (CNPG replica 1)
haven-platform-2               1/1 Running   3d20h  (CNPG replica 2)
iyziops-api-7d4cdcc485-pgbgh   1/1 Running   21h
iyziops-ui-d4769677d-6rwbf     1/1 Running   20h
```

API + UI sağlıklı, son deploy 20-21 saat önce (PR #174 sonrası digest pin commit'lerinden).

## 11. Unhealthy Pods (cluster-wide)

```
harbor-system   harbor-registry-7f6d8d5dd6-b5gct   0/2 ContainerCreating   5h6m
tenant-demo     app-pg-1-initdb-*                  0/1 Error               36h × 7 pod
```

`harbor-registry` pod 5h ContainerCreating → Harbor Application Degraded durumunu açıklıyor. Büyük ihtimal PVC bind / image pull / init issue. Sprint 3 scope'unda, bu sprintte dokunulmayacak — **ama** Harbor project create (tenant bootstrap adım 7) Harbor Core üzerinden gidiyor; Core sağlıklı, Registry'nin Degraded olması project create'i bloke etmiyor (verify gerekli).

## 12. Action Items → Faz 2.V / 2.0 / 2.A

**2.V.1 auto-unseal** — Vault şu an unsealed, pod restart'a dayanıksız. Transit unseal (ikinci mini-Vault) veya Hetzner'da mevcut olmayan KMS için alternatif. Karar noktası.

**2.V.2 ClusterSecretStore** — operator + CRD hazır, bir `ClusterSecretStore vault-backend` YAML + Vault token auth yeter. En hızlı kazanç.

**2.V.3 DATABASE_URL** — aday 1, düşük risk (ESO kv store → K8s Secret overwrite → iyziops-api rollout).

**2.V.5 Keycloak** — `KC_BOOTSTRAP_ADMIN_PASSWORD` + `KC_DB_PASSWORD` deploy env'den Vault'a. **Deploy spec değişir** (env → envFrom secretRef → ExternalSecret hedef secret). En karmaşık migration.

**2.0.4 Forgot Password SMTP** — realm JSON'a SMTP block + Mailpit dev deploy. Keycloak Deployment env'de SMTP yok → realm-level olmalı.

**2.0.5 GitHub IdP** — realm JSON broker config + ayrı OAuth App. Secret: `kv/platform/keycloak-github-idp` Vault path.

**2.0.7 Request access** — `/access-requests` endpoint canlı test lazım. UI formundan submit + 201 kanıtı. Rate-limit X-Forwarded-For fix ayrı.

**2.0.1 /tenants timeout** — canlı browser gerekli. Chrome DevTools + hubble simültane.

**2.A.1** — baseline hazır; fresh `bootstrap-audit-2026-04-21` tenant yaratılınca fan-out doğrulama.

## 13. Memory updates (bu audit sonrası)

- `project_github_oauth_placeholder_bug.md` → **RESOLVED** stamp (secret zaten patched).
- `vault_credentials_20260417.md` → follow-up note: auto-unseal henüz yok.
- `RESUME_HERE.md` → Faz 2.0/2.V/2.A sprint başladı, audit complete.

## 14. Scratch log'lar (session)

- `logs/scratch-vault-state-202604210647.log`
- `logs/scratch-eso-state-202604210647.log`
- `logs/scratch-secrets-inventory-202604210647.log`
- `logs/scratch-tenant-argocd-202604210647.log`
- `logs/scratch-vault-keycloak-locate-202604210648.log`
- `logs/scratch-vault-seal-202604210648.log`
- `logs/scratch-keycloak-realm-202604210648.log`

Sprint sonunda `logs/` temizlenecek (sadece `.gitkeep`).
