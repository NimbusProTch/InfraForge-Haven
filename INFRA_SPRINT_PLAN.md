# Haven Platform — Infrastructure Sprint Planı

> **Kapsam**: Bu plan yalnızca **infrastructure/k8s katmanını** kapsar.
> Uygulama kodu sprint'leri için: [SPRINT_PLAN.md](SPRINT_PLAN.md)
> **Tarih**: 2026-03-28
> **Platform**: Hetzner Cloud · RKE2 v1.32.3 · Cilium 1.16 · Longhorn 1.7 · Gateway API v1.2.1
> **Compliance**: 15/15 PASS (2026-03-24)

---

## Mevcut Durum Tespiti

### Çalışan Altyapı ✅
| Bileşen | Namespace | Versiyon | HTTPRoute |
|---------|-----------|----------|-----------|
| Cilium CNI + Gateway API | kube-system | 1.16 | — |
| Longhorn Storage | longhorn-system | 1.7.1 | ❌ Eksik |
| cert-manager | cert-manager | v1.16.2 | — |
| kube-prometheus-stack (Prometheus + **Grafana**) | monitoring | 67.4.0 | ❌ Eksik |
| loki-stack | logging | 2.10.2 | — |
| Harbor | harbor-system | 1.16.2 | ✅ |
| MinIO | minio-system | 5.3.0 | ✅ (console + s3) |
| ArgoCD | argocd | 7.7.3 | ✅ |
| Keycloak + CNPG | keycloak | 2.4.4 | ✅ |
| Percona **Everest** | everest-system | 1.13.0 | ❌ Eksik |
| Hubble UI | kube-system | (Cilium built-in) | ❌ Eksik |
| Redis Operator | redis-system | 0.18.0 | — |
| RabbitMQ Operator | rabbitmq-system | latest | — |
| Haven API | haven-system | — | ✅ |

### Tespit Edilen Tüm Eksikler

| # | Eksik | Kritiklik | Sprint |
|---|-------|-----------|--------|
| a | Everest HTTPRoute | 🔴 Yüksek | **Sprint 0** |
| b | Grafana HTTPRoute | 🔴 Yüksek | **Sprint 0** |
| c | Longhorn HTTPRoute | 🔴 Yüksek | **Sprint 0** |
| d | Hubble UI HTTPRoute | 🔴 Yüksek | **Sprint 0** |
| e | CiliumNetworkPolicy per tenant | 🔴 Yüksek | **Sprint 1** |
| f | ResourceQuota per tenant | 🔴 Yüksek | **Sprint 1** |
| g | LimitRange per tenant | 🔴 Yüksek | **Sprint 1** |
| h | Harbor project per tenant otomasyonu | 🟠 Orta | **Sprint 2** |
| i | Loki multi-tenancy (X-Scope-OrgID) | 🟠 Orta | **Sprint 2** |
| j | Encryption at rest (etcd) | 🟠 Orta | **Sprint 3** |
| k | Pod-to-pod encryption (Cilium WireGuard) | 🟠 Orta | **Sprint 3** |
| l | K8s RBAC ↔ Keycloak OIDC mapping | 🟡 Düşük | **Sprint 4** |
| m | DNS — sslip.io → gerçek domain | 🟡 Düşük | **Sprint 5** |

---

## Sprint 0 — Gateway Tamamlama (HTTPRoutes)
**Süre**: 1 gün
**Öncelik**: 🔴 BLOCKER — Kritik UI'lar erişilemez durumda
**Bağımlılık**: Yok
**Dosya**: `infrastructure/environments/dev/manifests/gateway-api.yaml`

### IS0-01: Eksik HTTPRoute'ları Ekle ✅ (Bu sprint'te implement edildi)

| Servis | Hostname | Namespace | Service | Port |
|--------|----------|-----------|---------|------|
| Everest UI | `everest.46.225.42.2.sslip.io` | everest-system | everest-server | 8080 |
| Grafana | `grafana.46.225.42.2.sslip.io` | monitoring | kube-prometheus-stack-grafana | 80 |
| Longhorn UI | `longhorn.46.225.42.2.sslip.io` | longhorn-system | longhorn-frontend | 80 |
| Hubble UI | `hubble.46.225.42.2.sslip.io` | kube-system | hubble-ui | 80 |

- [x] 4 HTTPRoute objesi `gateway-api.yaml`'a eklendi
- [x] Certificate `haven-gateway-tls` SAN listesine 4 yeni hostname eklendi
- [x] `main.tf` locals'a `grafana_host`, `longhorn_host`, `hubble_host` eklendi

### IS0-02: Certificate SAN Güncellemesi ✅ (Bu sprint'te implement edildi)
- [x] `haven-gateway-tls` Certificate'ına yeni 4 hostname eklendi
- **Not**: cert-manager mevcut Certificate objesini günceller. Re-issue tetiklenir.
- **Not**: LetsEncrypt HTTP-01 challenge için tüm hostname'lerin LB IP'ye resolve olması gerekir — sslip.io bunu otomatik sağlar.

---

## Sprint 1 — Tenant İzolasyonu (Network + Resource Policies)
**Süre**: 1 hafta
**Öncelik**: 🔴 Yüksek — Multi-tenant güvenlik
**Bağımlılık**: Sprint 0

### IS1-01: CiliumNetworkPolicy per Tenant *(2 gün)*
- [ ] `platform/manifests/tenant-policies/network-policy.yaml.tpl` template oluştur
- [ ] Per-tenant policy kuralları:
  ```yaml
  # Tenant namespace'den dışarı çıkış yok (sadece izin verilenler)
  # Başka tenant namespace'lerine erişim yok
  # haven-system → tenant erişimi açık (deployment API)
  # monitoring namespace → tenant namespace scraping açık
  # kube-dns → açık (53/UDP)
  # egress: internet açık, diğer tenant namespace'leri kapalı
  ```
- [ ] `api/app/services/k8s_client.py`: tenant namespace oluşturulduğunda `CiliumNetworkPolicy` uygula
- [ ] Default-deny ingress + whitelist pattern kullan
- **Etkilenen Dosyalar**: `platform/manifests/tenant-policies/`, `api/app/services/k8s_client.py`

### IS1-02: ResourceQuota per Tenant *(1 gün)*
- [ ] `platform/manifests/tenant-policies/resource-quota.yaml.tpl` template:
  ```yaml
  # dev tier:     cpu=4, memory=8Gi, pods=20, pvc=5
  # standard tier: cpu=16, memory=32Gi, pods=50, pvc=20
  # premium tier: cpu=64, memory=128Gi, pods=200, pvc=100
  ```
- [ ] Tier bilgisini `Tenant.tier` DB alanından oku
- [ ] `k8s_client.py`: `create_namespace()` → ResourceQuota oluştur
- [ ] Tenant tier değiştiğinde quota'yı güncelle (`PATCH` ResourceQuota)
- **Etkilenen Dosyalar**: `platform/manifests/tenant-policies/`, `api/app/services/k8s_client.py`, `api/app/models/tenant.py`

### IS1-03: LimitRange per Tenant *(1 gün)*
- [ ] `platform/manifests/tenant-policies/limit-range.yaml.tpl` template:
  ```yaml
  # Container default limit: cpu=500m, memory=512Mi
  # Container max: cpu=4, memory=4Gi
  # Container min: cpu=10m, memory=32Mi
  # PVC max: 50Gi (dev), 200Gi (standard), 1Ti (premium)
  ```
- [ ] Namespace oluşturulurken LimitRange uygula
- [ ] Mevcut namespace'ler için migration script: `scripts/backfill-limit-ranges.sh`
- **Etkilenen Dosyalar**: `platform/manifests/tenant-policies/`, `api/app/services/k8s_client.py`

### IS1-04: Namespace Provisioning Refactor *(1 gün)*
- [ ] Mevcut dağınık namespace oluşturma kodunu `k8s_client.create_tenant_namespace()` metodunda topla
- [ ] Namespace oluşturma sırası:
  1. Namespace (PSA label: restricted)
  2. ResourceQuota
  3. LimitRange
  4. CiliumNetworkPolicy
  5. Haven system ServiceAccount + RBAC
- [ ] Idempotent: `--dry-run=client | apply` pattern
- **Etkilenen Dosyalar**: `api/app/services/k8s_client.py`

---

## Sprint 2 — Harbor + Loki Multi-Tenancy
**Süre**: 1 hafta
**Öncelik**: 🟠 Yüksek
**Bağımlılık**: Sprint 1

### IS2-01: Harbor Project per Tenant Otomasyonu *(2 gün)*
- [ ] `api/app/services/harbor_service.py` yeni servis:
  ```python
  async def create_project(tenant_slug: str) -> HarborProject
  async def delete_project(tenant_slug: str) -> None
  async def create_robot_account(tenant_slug: str) -> RobotCredentials
  async def get_push_secret(tenant_slug: str) -> K8sSecret
  ```
- [ ] Harbor Admin API: `POST /api/v2.0/projects`
  - Project name: `tenant-{slug}`
  - Private: true
  - Storage quota: tier'a göre (dev: 20Gi, standard: 100Gi, premium: 500Gi)
- [ ] Robot account per tenant: push/pull hakları
- [ ] K8s imagePullSecret oluştur: `harbor-{slug}-pull-secret`
- [ ] Tenant silindiğinde Harbor project + robot account sil
- [ ] `HARBOR_ADMIN_URL`, `HARBOR_ADMIN_PASSWORD` → K8s Secret'tan oku (hardcoded kaldır)
- **Etkilenen Dosyalar**: `api/app/services/harbor_service.py` (yeni), `api/app/services/tenant_service.py`

### IS2-02: Loki Multi-Tenancy *(2 gün)*
- [ ] `infrastructure/environments/dev/helm-values/logging.yaml` güncelle:
  ```yaml
  loki:
    auth_enabled: true
    config:
      auth_enabled: true
  ```
- [ ] Promtail `pipeline_stages` → her pod'un namespace'inden `X-Scope-OrgID` header ekle:
  ```yaml
  # tenant-{slug} namespace → orgID: {slug}
  # system namespaces → orgID: system
  ```
- [ ] Haven API Grafana veri kaynağı konfigürasyonu:
  - Her tenant için `X-Scope-OrgID: {slug}` header ile Loki sorgusu
  - `GET /tenants/{slug}/apps/{app_slug}/logs` → `X-Scope-OrgID: {slug}`
- [ ] Grafana provisioning: per-tenant datasource (Loki + orgID header)
- [ ] `infrastructure/environments/dev/main.tf`: loki-stack `auth_enabled` template var ekle
- **Etkilenen Dosyalar**: `infrastructure/environments/dev/helm-values/logging.yaml`, `api/app/services/observability_service.py`

### IS2-03: Grafana Admin Password Secret *(0.5 gün)*
- [ ] `helm-values/monitoring.yaml`: `adminPassword` template var ekle (`${grafana_admin_password}`)
- [ ] `main.tf`: `grafana_admin_password = var.grafana_admin_password` (zaten var, template'i düzelt)
- [ ] `variables.tf`: `grafana_admin_password` sensitive=true (zaten var)
- **Etkilenen Dosyalar**: `infrastructure/environments/dev/helm-values/monitoring.yaml`

---

## Sprint 3 — Encryption at Rest + in Transit
**Süre**: 1 hafta
**Öncelik**: 🟠 Orta
**Bağımlılık**: Sprint 0

### IS3-01: Encryption at Rest — etcd Secret Encryption *(2 gün)*
- [ ] **Tespit**: Mevcut RKE2 config'de `secrets-encryption: true` yok → etcd'deki K8s Secret'lar plaintext
- [ ] `infrastructure/environments/dev/main.tf`: RKE2 master config'e ekle:
  ```yaml
  secrets-encryption: true
  ```
- [ ] Yeni cluster'lar için otomatik aktif — mevcut cluster için:
  ```bash
  rke2 secrets-encrypt enable
  rke2 secrets-encrypt rotate
  rke2 secrets-encrypt reencrypt
  ```
- [ ] `scripts/enable-secrets-encryption.sh` migration script yaz
- [ ] Doğrulama: `kubectl get pod -n kube-system kube-apiserver-* -o yaml | grep encryption`
- **Etkilenen Dosyalar**: `infrastructure/environments/dev/main.tf`, `scripts/enable-secrets-encryption.sh` (yeni)

### IS3-02: Encryption at Rest — Longhorn Volume Encryption *(1 gün)*
- [ ] **Tespit**: Longhorn `StorageClass` encryption=false (default)
- [ ] `infrastructure/environments/dev/helm-values/longhorn.yaml` güncelle:
  - Default StorageClass encryption için Longhorn secret oluştur
  - `longhorn-crypto` K8s Secret (LUKS key)
  - StorageClass parameter: `encrypted: "true"`
- [ ] Mevcut PVC'ler için migration prosedürü belgele (backup → delete → re-create)
- **Etkilenen Dosyalar**: `infrastructure/environments/dev/helm-values/longhorn.yaml`

### IS3-03: Pod-to-Pod Encryption (Cilium WireGuard) *(1 gün)*
- [ ] **Tespit**: Cilium config'de `encryption.enabled: false` (belirtilmemiş = false)
- [ ] `infrastructure/environments/dev/main.tf`: RKE2 HelmChartConfig güncelle:
  ```yaml
  encryption:
    enabled: true
    type: wireguard
    wireguard:
      userspaceFallback: true
  ```
- [ ] **Bağımlılık**: Linux kernel 5.6+ gerekir (Ubuntu 22.04 → kernel 5.15 ✅)
- [ ] **Uyarı**: `kubeProxyReplacement: true` + WireGuard → `kube-proxy` tamamen devre dışı kalır (zaten öyle)
- [ ] Doğrulama: `cilium status | grep Encryption`
- [ ] Performance impact notu: ~5-10% throughput azalması (kabul edilebilir)
- **Etkilenen Dosyalar**: `infrastructure/environments/dev/main.tf`

---

## Sprint 4 — K8s RBAC ↔ Keycloak OIDC
**Süre**: 1 hafta
**Öncelik**: 🟡 Düşük-Orta
**Bağımlılık**: Sprint 0, uygulama Sprint 4 (S4-01: Keycloak Realm Otomasyonu)

### IS4-01: RKE2 OIDC Konfigürasyonu *(2 gün)*
- [ ] **Tespit**: RKE2 kube-apiserver'da `--oidc-issuer-url` yok → Keycloak token'ları doğrudan K8s'e sunulamıyor
- [ ] `infrastructure/environments/dev/main.tf`: master config'e OIDC ekle:
  ```yaml
  kube-apiserver-arg:
    - "oidc-issuer-url=https://keycloak.46.225.42.2.sslip.io/realms/haven"
    - "oidc-client-id=kubernetes"
    - "oidc-username-claim=preferred_username"
    - "oidc-groups-claim=groups"
    - "oidc-username-prefix=oidc:"
    - "oidc-groups-prefix=oidc:"
  ```
- [ ] Keycloak'ta `kubernetes` OIDC client oluştur (keycloak/haven-realm.json güncelle)
- [ ] `keycloak/setup-realm.sh`: kubernetes client + `groups` mapper ekle
- **Etkilenen Dosyalar**: `infrastructure/environments/dev/main.tf`, `keycloak/haven-realm.json`, `keycloak/setup-realm.sh`

### IS4-02: K8s ClusterRole/RoleBinding Şablonları *(2 gün)*
- [ ] `platform/manifests/rbac/` dizini oluştur
- [ ] `platform/manifests/rbac/tenant-admin-role.yaml`:
  ```yaml
  # Keycloak group: oidc:tenant_{slug}_admin
  # Permissions: deploy, scale, view logs, manage services (namespace-scoped)
  ```
- [ ] `platform/manifests/rbac/tenant-member-role.yaml`:
  ```yaml
  # Keycloak group: oidc:tenant_{slug}_member
  # Permissions: view only (read deployments, pods, services)
  ```
- [ ] `platform/manifests/rbac/platform-admin-clusterrole.yaml`:
  ```yaml
  # Keycloak group: oidc:haven_admins
  # Permissions: cluster-admin (full access)
  ```
- [ ] Haven API, tenant RBAC için Keycloak group'larını otomatik oluşturur (S4-01 app sprint ile koordine)
- **Etkilenen Dosyalar**: `platform/manifests/rbac/` (yeni dizin)

---

## Sprint 5 — Gerçek Domain + DNS Otomasyonu
**Süre**: 1 hafta
**Öncelik**: 🟡 Düşük
**Bağımlılık**: Sprint 0

### IS5-01: External-DNS Aktivasyonu *(1 gün)*
- [ ] **Tespit**: `enable_external_dns = false` (devre dışı), `cloudflare_api_token = ""` (boş)
- [ ] `variables.tf`: `domain` default'u `haven.dev` → gerçek domain
- [ ] `terraform.tfvars`: `enable_external_dns = true`, `cloudflare_api_token = "..."`, `external_dns_domain_filters = ["yourdomain.com"]`
- [ ] `infrastructure/environments/dev/helm-values/external-dns.yaml` değerlerini gözden geçir
- **Etkilenen Dosyalar**: `infrastructure/environments/dev/variables.tf`, `infrastructure/environments/dev/terraform.tfvars`

### IS5-02: gateway-api.yaml → Gerçek Domain Migrasyonu *(1 gün)*
- [ ] `infrastructure/environments/dev/manifests/gateway-api.yaml`:
  - `*.46.225.42.2.sslip.io` → `*.yourdomain.com` (tüm hostname'ler)
  - Certificate SAN listesini gerçek domainlerle güncelle
- [ ] `main.tf` locals: `sslip.io` formatından `${var.domain}` formatına geç
  - `harbor_host = "harbor.${var.domain}"` vb.
- [ ] cert-manager ClusterIssuer: LetsEncrypt production (mevcut) → DNS-01 challenge ile wildcard cert (isteğe bağlı)
- **Etkilenen Dosyalar**: `infrastructure/environments/dev/manifests/gateway-api.yaml`, `infrastructure/environments/dev/main.tf`

### IS5-03: Wildcard Certificate *(1 gün)*
- [ ] Mevcut: per-SAN cert (her hostname tek tek)
- [ ] Hedef: `*.yourdomain.com` wildcard cert → DNS-01 challenge (Cloudflare)
- [ ] cert-manager `dns01` solver + Cloudflare API token secret
- [ ] Gateway `certificateRefs` → wildcard secret
- **Etkilenen Dosyalar**: `infrastructure/environments/dev/manifests/gateway-api.yaml`

---

## Sprint Bağımlılık Grafiği

```
Sprint 0 (HTTPRoutes)     ← TAMAMLANDI (bu commit)
    ↓
Sprint 1 (Tenant Policies)
    ↓
Sprint 2 (Harbor + Loki)
    ↓
Sprint 3 (Encryption)     Sprint 4 (RBAC + OIDC)     Sprint 5 (DNS)
    ↓                           ↓                          ↓
                        ← Production Ready →
```

---

## Notlar

### Neden sslip.io?
LetsEncrypt HTTP-01 challenge için gerçek DNS resolve gerekir. `sslip.io` LB IP'yi hostname'e encode eder (`46.225.42.2.sslip.io` → `46.225.42.2`). Gerçek domain hazır olduğunda tek bir `gateway-api.yaml` ve `main.tf` locals değişikliği yeterli.

### Cilium 1.16 Bilinen Sorunlar
- `GatewayClass.status.supportedFeatures` → `Unknown` (cosmetic, functional değil)
- NodePort BPF bug → gateway-proxy nginx DaemonSet ile workaround aktif

### Encryption at Rest Sıralaması
Önce etcd secret encryption, sonra Longhorn volume encryption, sonra WireGuard. Sıra önemli: WireGuard tüm pod trafiğini etkiler, önce etcd'yi güvenceye almak gerekir.
