# Haven Platform — Kapsamlı Sprint Planı

> **Hedef**: Outplane.com / Railway.app seviyesinde enterprise self-hosted PaaS
> **Tarih**: 2026-03-28
> **Mevcut Durum**: Phase 1 Sprint 2 tamamlandı — Build/deploy pipeline + temel UI çalışıyor
> **Geliştirme Ortamı**: Hetzner RKE2 + Cilium + Longhorn + CNPG + BuildKit

---

## Mevcut Durum Özeti (Repo Analizi)

### Çalışan Özellikler ✅
- RKE2 cluster (Cilium CNI, Longhorn storage, Cert-Manager, Harbor, MinIO)
- CNPG PostgreSQL operator + tenant DB
- ArgoCD 7.7.3 GitOps
- Keycloak 26.1 (tek realm, start-dev)
- FastAPI backend (7 router, 8 servis, JWT auth çoğu endpoint'te mevcut)
- BuildKit pipeline (Nixpacks auto-detect, private repo clone, Harbor push)
- Next.js 14 UI (NextAuth + Keycloak + GitHub OAuth)
- Managed Services altyapısı: CNPG (Postgres), OpsTree Redis, RabbitMQ CRD (provizyon kodu yazılı)
- Webhook auto-deploy iskelet (HMAC doğrulama mevcut)
- HPA konfigürasyonu (varsayılan 1-5 replika, %70 CPU)

### Kritik Eksikler 🔴
1. **Güvenlik**: `SECRET_KEY = "change-me-in-production"`, `HARBOR_ADMIN_PASSWORD = "Harbor12345"` hardcoded
2. **Güvenlik**: GitHub OAuth token `localStorage`'da (XSS riski)
3. **Veri Bütünlüğü**: App silindiğinde K8s kaynakları (Deployment, Service, HTTPRoute) silinip silinmediği doğrulanmamış
4. **RBAC**: Tenant-level yetkilendirme yok — authenticated her kullanıcı her tenant'ı görebilir
5. **GitOps**: `GITOPS_BRANCH = "feature/platform-v2"` (main olmalı)
6. **Test**: Sıfır test (pytest hazır ama test dosyası yok)
7. **Observability**: Prometheus/Grafana deployed ama uygulamalara bağlı değil — gerçek metrik yok
8. **Keycloak**: Per-tenant realm otomasyonu yok (DB'de kaydediliyor ama Keycloak Admin API çağrısı yapılmıyor)
9. **MySQL/MongoDB**: Percona Everest/operator kurulmamış (sadece kod iskelet var)
10. **Managed Service → App**: Bağlantı UI mevcut değil (backend kodu var, UI AddServiceModal yok/eksik)

---

## Sprint Sıralaması ve Bağımlılıklar

```
Sprint 0 (Güvenlik + Temel Düzeltmeler)
    ↓
Sprint 1 (Managed Services Tamamlama)
    ↓
Sprint 2 (Observability — Gerçek Metrikler)
    ↓
Sprint 3 (Monorepo + Akıllı Detection)    Sprint 4 (Tenant RBAC + Multi-User)
    ↓                                           ↓
Sprint 5 (Staging / Preview Environments)
    ↓
Sprint 6 (Custom Domain + Wildcard TLS)
    ↓
Sprint 7 (Takım Yönetimi + SSO)
    ↓
Sprint 8 (Billing + Usage Tracking)
    ↓
Sprint 9 (Audit Logging + Compliance)
    ↓
Sprint 10 (Enterprise Hardening + Production)
```

---

## Sprint 0 — Kritik Güvenlik ve Temel Düzeltmeler
**Süre**: 1 hafta
**Öncelik**: 🔴 BLOCKER — Production'a almadan önce zorunlu
**Bağımlılık**: Yok

### Güvenlik Açıkları

**S0-01: Secret Yönetimi** *(2 gün)*
- [ ] `SECRET_KEY`, `HARBOR_ADMIN_PASSWORD`, `WEBHOOK_SECRET` — hardcoded değerleri kaldır
- [ ] K8s Secret objelerine taşı (`kubectl create secret generic haven-secrets`)
- [ ] `config.py`'de `SecretStr` Pydantic tipi kullan, log'a asla basılmasın
- [ ] `.env.example` dosyası oluştur (gerçek değerler yok, sadece key listesi)
- [ ] ArgoCD `argocd-vault-plugin` veya SealedSecrets entegrasyonu planla (Phase 2)
- **Etkilenen Dosyalar**: `api/app/config.py`, `platform/manifests/`, `infrastructure/environments/dev/`

**S0-02: GitHub OAuth Token — localStorage Güvenlik Düzeltmesi** *(1 gün)*
- [ ] `localStorage.setItem("haven_github_oauth_token", token)` kaldır
- [ ] Token'ı NextAuth session'ına taşı (`session.githubToken`)
- [ ] Backend `/api/v1/tenants/{slug}/github/token` endpoint'i: token'ı DB'ye kaydet, session üzerinden ilet
- [ ] `ui/lib/api.ts` tüm GitHub API çağrılarında session token'ı kullan
- **Etkilenen Dosyalar**: `ui/app/github/callback/page.tsx`, `ui/lib/api.ts`, `ui/lib/auth.ts`

**S0-03: Tenant-Level RBAC** *(2 gün)*
- [ ] `CurrentUser` dependency: JWT'den `sub` (user ID) ve `tenant_access` claim'lerini çıkar
- [ ] Her tenant kaynağına (app, service, deployment) `tenant_id → user` mapping doğrulaması ekle
- [ ] Keycloak'ta `tenant_{slug}_admin` ve `tenant_{slug}_member` role'leri planla
- [ ] Şimdilik: `tenants` tablosuna `owner_user_id` kolonu ekle, yalnızca owner erişebilsin
- **Etkilenen Dosyalar**: `api/app/auth/jwt.py`, `api/app/routers/*.py`

### Veri Bütünlüğü

**S0-04: App Silme — K8s Garbage Collection Doğrulaması** *(1 gün)*
- [ ] `deploy_service.py`'deki `delete_app` fonksiyonunu incele — Deployment, Service, HTTPRoute, HPA, ConfigMap, Secrets siliniyor mu?
- [ ] `K8sClient.delete_app_resources()` ile tam cleanup listesi oluştur
- [ ] Silme sırası: HPA → Deployment → Service → HTTPRoute → ConfigMap → PVC (varsa)
- [ ] `--grace-period=30` ile graceful shutdown
- [ ] Silme başarısız olursa app "deleting" durumunda kalsın, zombie kaynak olmasın

**S0-05: GitOps Branch Düzeltmesi** *(1 saat)*
- [ ] `api/app/config.py`: `GITOPS_BRANCH = "main"` (feature/platform-v2 → main)
- [ ] `platform/argocd/app-of-apps.yaml`: `targetRevision: main`
- [ ] `platform/argocd/apps/*.yaml`: tüm Application'larda `targetRevision: main`
- [ ] `platform/argocd/applicationsets/*.yaml`: aynı düzeltme

**S0-06: Temel Test Altyapısı** *(2 gün)*
- [ ] `api/tests/conftest.py`: pytest fixtures (async DB session, mock K8s client, mock Keycloak)
- [ ] `api/tests/test_health.py`: health endpoint smoke tests
- [ ] `api/tests/test_tenants.py`: CRUD + auth doğrulama
- [ ] `api/tests/test_applications.py`: CRUD + K8s mock
- [ ] `api/tests/test_deployments.py`: build trigger + status polling mock
- [ ] CI: GitHub Actions workflow (lint → test → build)
- [ ] Coverage hedefi: %60 (başlangıç)

---

## Sprint 1 — Managed Services Tamamlama
**Süre**: 2 hafta
**Öncelik**: 🟠 Yüksek
**Bağımlılık**: Sprint 0 tamamlanmalı

### Operator Kurulumları

**S1-01: Percona Everest Entegrasyonu** *(3 gün)*
- [ ] `infrastructure/environments/dev/main.tf`: Percona Everest operator Helm chart ekle
  - `percona/everest` chart, `everest-system` namespace
  - Desteklenen: PostgreSQL, MySQL, MongoDB
- [ ] `infrastructure/modules/rke2-cluster/`: CRD bootstrap manifests (everest CRDs)
- [ ] Everest `DatabaseCluster` CRD'yi incele, mevcut `managed_service.py` ile uyumlu hale getir
- [ ] MySQL provisioning: `managed_service.py`'e `_provision_mysql()` metodu tamamla
- [ ] MongoDB provisioning: `managed_service.py`'e `_provision_mongodb()` metodu tamamla
- [ ] Tier mapping: `dev` (1 replika, 5Gi), `standard` (3 replika, 20Gi), `premium` (3 replika, 100Gi, PITR)

**S1-02: Redis Sentinel/Cluster Mode** *(2 gün)*
- [ ] OpsTree Redis Operator `v1beta2` CRD kurulumunu doğrula (`k8s/client.py`)
- [ ] Redis Sentinel (HA): 3 replika + 3 sentinel, quorum=2
- [ ] Redis Cluster mode (sharding): 6 node (3 master + 3 replica)
- [ ] `dev` tier: single instance, `standard` tier: sentinel, `premium` tier: cluster
- [ ] Redis password: K8s Secret otomatik oluştur, `{name}-redis-secret` adıyla

**S1-03: RabbitMQ Cluster Operator Kurulumu** *(1 gün)*
- [ ] RabbitMQ Cluster Operator Helm chart: `infrastructure/environments/dev/main.tf`
- [ ] `rabbitmq-system` namespace, `rabbitmq.com/v1beta1` CRD
- [ ] Virtual host per-tenant: `/{tenant_slug}`
- [ ] Management UI HTTPRoute ekle (RabbitMQ Management, port 15672)
- [ ] Secret format: `{username}:{password}@{svc}.{ns}.svc:5672/{vhost}`

### Backend Tamamlama

**S1-04: Managed Service Status Polling** *(1 gün)*
- [ ] `managed_service.py`: CRD status'u gerçek zamanlı oku (CNPG `Cluster.status.conditions`, Redis `Redis.status`, RabbitMQ `RabbitmqCluster.status`)
- [ ] Background task: Her 10 saniyede provisioning servislerini kontrol et → DB'yi güncelle
- [ ] Failed durumu: hata mesajını `ManagedService.error_message` alanına kaydet (schema ekle)
- [ ] WebSocket veya SSE ile UI'a anlık durum push'u (Sprint 1 son kapsamında)

**S1-05: Managed Service → Application Bağlantısı** *(2 gün)*
- [ ] `deploy_service.py`: `Application.connected_services` listesini Deployment env var'larına enjekte et
- [ ] Secret ref pattern: `envFrom.secretRef.name: {service_secret_name}`
- [ ] `applications` tablosuna `connected_service_ids` (JSON array) kolonu ekle
- [ ] `PATCH /tenants/{slug}/apps/{app_slug}/services` endpoint: bağlantı ekle/kaldır
- [ ] Bağlantı değiştiğinde otomatik rolling restart tetikle

**S1-06: Managed Services UI — Tam İmplementasyon** *(2 gün)*
- [ ] `AddServiceModal`: service type seçimi (Postgres/MySQL/MongoDB/Redis/RabbitMQ), tier seçimi, isim
- [ ] Services sekmesi: mevcut servisler listesi, durum badge (Provisioning/Ready/Failed)
- [ ] Servis detayı: connection string kopyala butonu (masked password, unmask toggle)
- [ ] App ayarlarında "Connected Services" bölümü: servis ekle/çıkar dropdown
- [ ] Servis silme: confirm dialog + "Bu servise bağlı X app var, silmek istediğinizden emin misiniz?"
- [ ] Provisioning progress: spinner + log stream (CRD events SSE)

---

## Sprint 2 — Observability (Gerçek Metrikler)
**Süre**: 2 hafta
**Öncelik**: 🟠 Yüksek
**Bağımlılık**: Sprint 0

### Backend Wiring

**S2-01: Prometheus Scraping — App Metrikleri** *(2 gün)*
- [ ] Her deploy edilen app için `ServiceMonitor` CRD oluştur (rancher-monitoring CRD mevcut)
- [ ] Default metrics path: `/metrics` (konfig edilebilir, `Application.metrics_path`)
- [ ] Eğer app Prometheus expose etmiyorsa: nginx sidecar metrics exporter ekle (isteğe bağlı)
- [ ] `deploy_service.py`: `ServiceMonitor` oluştur/sil lifecycle'a bağla
- [ ] Tenant izolasyonu: `namespace: tenant-{slug}` label ile filtreleme

**S2-02: Grafana Loki — Uygulama Logları** *(2 gün)*
- [ ] `infrastructure/environments/dev/main.tf`: Loki Helm chart ekle (`grafana/loki-stack`)
- [ ] `loki-system` namespace, S3 backend → MinIO (mevcut)
- [ ] Fluentbit → Loki pipeline (Banzai logging operator mevcut → Loki output ekle)
- [ ] Per-tenant log filtreleme: `namespace=tenant-{slug}` label
- [ ] Retention: 30 gün (dev), 90 gün (prod)

**S2-03: Grafana Mimir — Uzun Vadeli Metrikler** *(1 gün)*
- [ ] `infrastructure/environments/dev/main.tf`: Grafana Mimir Helm chart
- [ ] Prometheus → Mimir remote_write konfigürasyonu
- [ ] Retention: 90 gün (dev), 1 yıl (prod)
- [ ] `mimir-system` namespace, MinIO backend

**S2-04: Grafana Tempo — Distributed Tracing** *(2 gün)*
- [ ] `infrastructure/environments/dev/main.tf`: Grafana Tempo + OpenTelemetry Collector
- [ ] Auto-instrumentation: Python (opentelemetry-auto-instrumentation), Node.js (auto)
- [ ] Deploy sırasında `OTEL_EXPORTER_OTLP_ENDPOINT` env var otomatik inject
- [ ] Tempo → MinIO backend (S3-compatible)

**S2-05: Observability API Endpoints** *(2 gün)*
- [ ] `api/app/routers/observability.py` yeni router
- [ ] `GET /tenants/{slug}/apps/{app_slug}/metrics` → Prometheus HTTP API sorgusu
  - CPU usage, Memory usage, Request rate, Error rate, P95/P99 latency
- [ ] `GET /tenants/{slug}/apps/{app_slug}/logs` → Loki HTTP API (SSE stream)
  - Query params: `since`, `limit`, `filter`
- [ ] `GET /tenants/{slug}/apps/{app_slug}/traces` → Tempo HTTP API
  - Son 10 trace, span breakdown
- [ ] `GET /tenants/{slug}/apps/{app_slug}/events` → K8s events (CrashLoop, OOM, etc.)

**S2-06: Observability UI — Gerçek Veri** *(3 gün)*
- [ ] `ObservabilityTab` component'ini mock'tan gerçek API'ye bağla
- [ ] CPU/Memory grafik: Recharts + 15 dakika/1 saat/24 saat/7 gün seçici
- [ ] Log viewer: gerçek Loki stream, ANSI renk desteği, regex filtre, download butonu
- [ ] Request metrics: req/sec, error rate, latency histogram
- [ ] Traces: span timeline görselleştirme (basit Gantt chart)
- [ ] K8s events timeline: CrashLoop, OOM, Eviction, ImagePull hatalarını göster

---

## Sprint 3 — Monorepo + Akıllı Detection
**Süre**: 1 hafta
**Öncelik**: 🟡 Orta-Yüksek
**Bağımlılık**: Sprint 0

**S3-01: Monorepo Build Context** *(2 gün)*
- [ ] `Application.dockerfile_path` ve `Application.build_context` alanları zaten var — UI'a ekle
- [ ] GitHub API tree endpoint (`/repos/{owner}/{repo}/git/trees/{sha}?recursive=1`) ile dizin listele
- [ ] `api/app/routers/github.py`: `GET /github/repos/{owner}/{repo}/tree` endpoint tamamla
- [ ] UI'da "Build Context" dropdown: repo'nun dizinlerini listele
- [ ] UI'da "Dockerfile Path" dropdown: tespit edilen Dockerfile'ları listele
- [ ] `build_service.py`: `git sparse-checkout` ile sadece `build_context` dizinini clone et (büyük monorepo'lar için)

**S3-02: Gelişmiş Dependency Detection** *(2 gün)*
- [ ] `detection_service.py` genişlet:
  - Python: `requirements.txt`, `pyproject.toml`, `Pipfile` — SQLAlchemy/Prisma → Postgres, redis-py → Redis, pika → RabbitMQ
  - Node.js: `package.json` dependencies — Prisma/TypeORM/Sequelize → Postgres, ioredis/redis → Redis, amqplib → RabbitMQ
  - Go: `go.mod` — gorm/pgx → Postgres, go-redis → Redis
  - Ruby: `Gemfile` — activerecord/pg → Postgres
  - PHP: `composer.json` — laravel/doctrine → Postgres
- [ ] Detection sonucunu `Application.detected_deps` JSON alanına kaydet (zaten var)
- [ ] Deploy sırasında eksik managed service varsa UI'da uyarı: "Bu app Postgres kullanıyor ama bağlı servis yok"

**S3-03: Multi-App Monorepo** *(2 gün)*
- [ ] Tek repo'dan birden fazla app deploy etme desteği
- [ ] `Application.subdirectory` alan: hangi alt dizin bu app'e karşılık gelir
- [ ] Webhook filter: sadece `subdirectory` ile ilgili commit'lerde build tetikle (changed files API)
- [ ] UI'da "Add Another App from Same Repo" butonu

---

## Sprint 4 — Tenant RBAC + Multi-User
**Süre**: 2 hafta
**Öncelik**: 🟠 Yüksek (Sprint 3 ile paralel yürütülebilir)
**Bağımlılık**: Sprint 0

**S4-01: Keycloak Realm Otomasyonu** *(3 gün)*
- [ ] `api/app/services/keycloak_service.py` yeni servis:
  - `create_realm(tenant_slug)`: Keycloak Admin REST API ile realm oluştur
  - `create_client(realm, client_id, redirect_uris)`: OIDC client oluştur
  - `create_user(realm, username, email, password)`: ilk admin user
  - `assign_role(realm, user_id, role)`: tenant_admin / tenant_member
  - `delete_realm(tenant_slug)`: tenant silindiğinde realm'i de sil
- [ ] Tenant oluşturma akışına realm otomasyonu ekle
- [ ] Realm-per-tenant izolasyonu: her müşteri kendi login sayfası, kendi kullanıcı veritabanı
- [ ] Admin API token: `KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD` env var (K8s Secret)

**S4-02: Tenant Üyelik Sistemi** *(3 gün)*
- [ ] `tenant_members` tablosu: `tenant_id`, `user_id` (Keycloak sub), `role` (owner/admin/member/viewer)
- [ ] `POST /tenants/{slug}/members` — Üye davet et (email → Keycloak realm'ine user oluştur)
- [ ] `GET /tenants/{slug}/members` — Üye listesi
- [ ] `PATCH /tenants/{slug}/members/{user_id}` — Rol değiştir
- [ ] `DELETE /tenants/{slug}/members/{user_id}` — Üye çıkar
- [ ] Permission guard: owner her şeyi yapabilir, admin deploy yapabilir, member sadece görüntüleyebilir, viewer sadece okuyabilir

**S4-03: Davet Email Akışı** *(1 gün)*
- [ ] `api/app/services/email_service.py`: SMTP / SendGrid entegrasyonu
- [ ] Davet linki: Keycloak token-based invitation URL
- [ ] Email şablonu: HTML, tenant adı, inviter adı, platform URL
- [ ] `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` env var

**S4-04: UI — Takım Yönetimi** *(2 gün)*
- [ ] Tenant ayarları → "Team" sekmesi
- [ ] Üye listesi tablosu: avatar, isim, email, rol badge, son aktivite
- [ ] Üye davet formu: email input + rol seçimi
- [ ] Pending invitations listesi
- [ ] Rol değiştirme dropdown (owner only)
- [ ] Üye silme butonu (confirm dialog)

---

## Sprint 5 — Staging / Preview Environments
**Süre**: 2 hafta
**Öncelik**: 🟡 Orta
**Bağımlılık**: Sprint 1, Sprint 3

**S5-01: Environment Modeli** *(2 gün)*
- [ ] `environments` tablosu: `application_id`, `name` (production/staging/preview), `branch`, `domain`, `env_vars`, `replicas`, `status`
- [ ] Her uygulama birden fazla environment'a sahip olabilir (varsayılan: production)
- [ ] `Environment.parent_app_id`: preview'lar main app'e bağlı
- [ ] `GET/POST /tenants/{slug}/apps/{app_slug}/environments`
- [ ] `GET/PATCH/DELETE /tenants/{slug}/apps/{app_slug}/environments/{env_name}`

**S5-02: Staging Environment** *(2 gün)*
- [ ] Staging: `main`/`master` branch → production, `staging` branch → staging namespace
- [ ] Staging namespace: `tenant-{slug}-staging`, ayrı K8s namespace
- [ ] Staging için ayrı managed service instance'ları (veya production'ı paylaş, konfig edilebilir)
- [ ] HTTPRoute: `staging-{app}.{lb-ip}.sslip.io`
- [ ] Env var override: staging'e özgü `DATABASE_URL`, `DEBUG=true` vb.

**S5-03: PR Preview Environments** *(3 gün)*
- [ ] GitHub webhook: `pull_request` event (opened/synchronize/closed)
- [ ] PR açıldığında: `tenant-{slug}-pr-{pr_number}` namespace oluştur, branch'i deploy et
- [ ] HTTPRoute: `pr-{pr_number}-{app}.{lb-ip}.sslip.io`
- [ ] PR kapatıldığında/merge olduğunda: namespace sil, kaynakları temizle
- [ ] GitHub PR comment: "✅ Preview deployed: https://pr-42-myapp.x.x.x.x.sslip.io"
- [ ] GitHub Checks API: preview URL'yi check status'una ekle
- [ ] Ephemeral DB: Preview için ayrı CNPG instance + prod DB snapshot restore (opsiyonel)
- [ ] TTL: 7 gün sonra otomatik sil (CronJob)

**S5-04: Environment UI** *(2 gün)*
- [ ] App detay sayfasında "Environments" sekmesi
- [ ] Environment kartları: production, staging, PR-42, PR-51...
- [ ] Her kart: URL, branch, son deploy, durum
- [ ] "Create Environment" butonu: isim + branch seç
- [ ] PR preview listesi: açık PR'lar + preview URL'leri

---

## Sprint 6 — Custom Domain + Wildcard TLS
**Süre**: 1 hafta
**Öncelik**: 🟠 Yüksek
**Bağımlılık**: Sprint 0

**S6-01: Custom Domain Backend** *(2 gün)*
- [ ] `Application.custom_domain` zaten var — DNS doğrulama ekle
- [ ] `POST /tenants/{slug}/apps/{app_slug}/domains` — domain ekle
- [ ] Domain doğrulama: DNS TXT record kontrol (`_haven-verify.domain.com TXT {token}`)
- [ ] Cloudflare API: `external-dns` opsiyonel (kendi DNS'ini kullananlar için TXT record talimatı ver)
- [ ] HTTPRoute'u güncelle: `hostnames: [custom_domain, default_sslip_domain]`
- [ ] `Certificate` CRD oluştur: cert-manager Let's Encrypt (HTTP-01 challenge)
- [ ] Status tracking: `DomainVerification` tablo: `domain`, `verified_at`, `certificate_status`

**S6-02: Wildcard Sertifika** *(1 gün)*
- [ ] `*.{lb-ip}.sslip.io` wildcard cert: DNS-01 challenge (Cloudflare API)
- [ ] `Certificate` CRD: `dnsNames: ["*.{lb_ip}.sslip.io"]`
- [ ] Tüm tenant HTTPRoute'ları bu wildcard cert'i paylaşabilir
- [ ] Cert-manager `ClusterIssuer` Cloudflare DNS-01 solver

**S6-03: Custom Domain UI** *(2 gün)*
- [ ] App ayarları → "Domains" sekmesi
- [ ] Domain listesi: default sslip.io domain (değiştirilemez) + custom domain'ler
- [ ] "Add Domain" formu: domain input
- [ ] DNS doğrulama talimatları: TXT record değeri + nameserver bilgisi
- [ ] Doğrulama durumu badge: Pending / Verified / Certificate Issued / Active
- [ ] "Verify Now" butonu (manual kontrol tetikler)
- [ ] Sertifika expiry gösterimi: "Expires in 87 days"

---

## Sprint 7 — Takım Yönetimi + Organization SSO
**Süre**: 2 hafta
**Öncelik**: 🟡 Orta
**Bağımlılık**: Sprint 4

**S7-01: Organization Kavramı** *(3 gün)*
- [ ] `organizations` tablosu: birden fazla tenant'ı gruplandırır
- [ ] `Organization.plan` alanı: free / starter / pro / enterprise
- [ ] Kullanıcı → Org member, Org → Tenant üyeliği
- [ ] Billing unit: Organization bazında (Sprint 8)
- [ ] `GET /organizations`, `POST /organizations`
- [ ] `GET /organizations/{org_slug}/tenants` — org'daki tüm tenant'lar

**S7-02: Enterprise SSO** *(2 gün)*
- [ ] Keycloak Identity Provider (IdP) federation:
  - SAML 2.0 (Azure AD, Okta, Google Workspace)
  - OIDC (custom IdP)
- [ ] Per-organization IdP konfigürasyonu (Keycloak Admin API)
- [ ] `Organization.sso_type`, `Organization.sso_metadata_url`, `Organization.sso_client_id`
- [ ] SSO-only mode: org üyelerine email/password login'i kapat

**S7-03: Audit Log Temeli** *(2 gün)*
- [ ] `audit_logs` tablosu: `actor_user_id`, `action`, `resource_type`, `resource_id`, `tenant_id`, `ip_address`, `user_agent`, `created_at`, `metadata` (JSON)
- [ ] Middleware: tüm mutasyon endpoint'lerinde otomatik log (POST/PATCH/DELETE)
- [ ] Actions: tenant.create, app.create, app.deploy, app.delete, service.create, member.invite, domain.add vb.
- [ ] `GET /organizations/{org_slug}/audit-logs` (pagination, filter by action/user/date)
- [ ] Audit log UI: tablo + zaman filtresi + kullanıcı filtresi (Sprint 9'da tam UI)

---

## Sprint 8 — Billing + Usage Tracking
**Süre**: 3 hafta
**Öncelik**: 🟡 Orta
**Bağımlılık**: Sprint 2 (gerçek metrikler), Sprint 7 (organization)

**S8-01: Usage Metrikleri Toplama** *(3 gün)*
- [ ] `usage_records` tablosu: `tenant_id`, `period` (YYYY-MM), `resource_type` (compute/storage/bandwidth/builds), `value`, `unit`
- [ ] CronJob: Her saat Prometheus'tan CPU/Memory kullanımını çek, `usage_records`'a yaz
- [ ] Build sayısı: her başarılı `Deployment` record → build usage +1
- [ ] Storage: Longhorn PVC boyutlarını sor (K8s API), günlük snapshot
- [ ] Bandwidth: Cilium Hubble flow metrics (namespace egress bytes)
- [ ] `GET /tenants/{slug}/usage?period=2026-03` — mevcut ay kullanımı

**S8-02: Fiyatlandırma Modeli** *(2 gün)*
- [ ] `plans` tablosu: name, cpu_limit, memory_limit, storage_limit, build_minutes/month, max_apps, max_custom_domains, price
- [ ] Varsayılan planlar:
  - **Free**: 0.5 vCPU, 512MB RAM, 5GB storage, 100 build dakika/ay, 3 app, 0 custom domain
  - **Starter**: 2 vCPU, 2GB RAM, 20GB storage, 500 build dakika/ay, 10 app, 1 custom domain — €19/ay
  - **Pro**: 8 vCPU, 8GB RAM, 100GB storage, 2000 build dakika/ay, unlimited app, 5 custom domain — €79/ay
  - **Enterprise**: Custom — teklif
- [ ] `Organization.plan_id` foreign key
- [ ] Limit aşıldığında: 429 Too Many Requests + UI uyarısı + email bildirimi

**S8-03: Stripe Entegrasyonu** *(3 gün)*
- [ ] Stripe SDK: `stripe` Python kütüphanesi
- [ ] `POST /billing/checkout` — Stripe Checkout Session oluştur
- [ ] Stripe webhook: `invoice.payment_succeeded`, `invoice.payment_failed`, `customer.subscription.updated`
- [ ] `Organization.stripe_customer_id`, `Organization.stripe_subscription_id`
- [ ] Fatura PDF: Stripe otomatik oluşturur, link UI'da göster
- [ ] Ödeme başarısız → grace period 3 gün → sonra servisler durdurulur (suspend, not delete)

**S8-04: Billing UI** *(2 gün)*
- [ ] Org ayarları → "Billing" sekmesi
- [ ] Mevcut plan badge + upgrade butonu
- [ ] Kullanım grafiği: CPU, Memory, Storage, Build Minutes (gauge charts)
- [ ] Fatura geçmişi: tarih, tutar, durum, PDF link
- [ ] Kredi kartı yönetimi (Stripe Elements embed)
- [ ] Plan karşılaştırma tablosu + upgrade flow

---

## Sprint 9 — Audit Logging + Compliance
**Süre**: 1 hafta
**Öncelik**: 🟡 Orta
**Bağımlılık**: Sprint 7

**S9-01: Tam Audit Log Implementasyonu** *(2 gün)*
- [ ] Tüm K8s operasyonlarını logla (build, deploy, delete, scale)
- [ ] Keycloak events senkronizasyonu: login, logout, password change, failed login
- [ ] Admin aksiyonları: quota değişikliği, üye davet/çıkarma, plan upgrade
- [ ] Log integrity: her log satırına HMAC signature (log tampering detection)
- [ ] Log export: CSV / JSON download, date range filter

**S9-02: GDPR / AVG Compliance** *(3 gün)*
- [ ] Data Processing Agreement (DPA) UI — müşteri kabul akışı
- [ ] Right to erasure: `DELETE /organizations/{org_slug}` — tüm veriyi sil (CNPG, K8s, Keycloak realm, audit logs)
- [ ] Data portability: tenant tüm data'sını export edebilsin (JSON tarball)
- [ ] Cookie consent (UI): minimal tracking, no third-party cookies
- [ ] Privacy Policy / Terms of Service sayfaları (platform admin tarafından konfig edilebilir URL)
- [ ] Data residency garantisi: tüm veri NL datacenters (Hetzner Falkenstein/Nuremberg + Cyso Amsterdam)
- [ ] VNG Haven compliance belgeleme (15/15 check otomatik rapor)

**S9-03: Notification Sistemi** *(2 gün)*
- [ ] `notifications` tablosu: `user_id`, `type`, `title`, `body`, `read_at`, `created_at`
- [ ] Event-driven: build failed → email + in-app, deploy success → in-app, billing warning → email + in-app
- [ ] In-app notification bell: UI'da okunmamış sayısı badge
- [ ] Email: SMTP/SendGrid şablon sistemi
- [ ] Webhook: Slack / Teams / Discord entegrasyonu (custom webhook URL per-org)
- [ ] `POST /organizations/{org_slug}/webhooks` — notification webhook tanımla

---

## Sprint 10 — Production Hardening + Enterprise
**Süre**: 3 hafta
**Öncelik**: 🟠 Yüksek (production'a geçiş için)
**Bağımlılık**: Sprint 0-9 tamamlanmalı

### Infrastructure Hardening

**S10-01: Production Cluster (Cyso / Leafcloud)** *(3 gün)*
- [ ] `infrastructure/environments/production/main.tf` oluştur
- [ ] Cyso Cloud / Leafcloud Amsterdam: OpenStack provider
- [ ] `infrastructure/modules/openstack-infra/`: VM, Network, LB, Security Groups
- [ ] Multi-AZ: AMS-1 + AMS-2
- [ ] 3 master + 3 worker (prod HA)
- [ ] Private network: inter-node trafiği private IP (--node-ip flag, RKE2 konfigürasyonu)
- [ ] Firewall: NodePort kaldır, sadece 80/443 (Gateway API), 6443 (K8s API, VPN only)

**S10-02: Secrets Management — Vault / SealedSecrets** *(2 gün)*
- [ ] HashiCorp Vault veya SealedSecrets seç (küçük ekip için SealedSecrets daha basit)
- [ ] SealedSecrets: `sealed-secrets-controller` Helm chart, `kubeseal` CLI
- [ ] Tüm platform secret'larını SealedSecret'a dönüştür
- [ ] ArgoCD: SealedSecret → Secret otomatik decrypt (controller in-cluster)
- [ ] Rotation: `kubeseal --re-encrypt` ile periyodik key rotation

**S10-03: Backup ve Disaster Recovery** *(3 gün)*
- [ ] CNPG barman: WAL archiving → MinIO S3, günlük snapshot
- [ ] CNPG PITR: Point-in-time recovery test (restore to 1 saat öncesi)
- [ ] Longhorn backup: MinIO S3, günlük volume snapshot
- [ ] Etcd backup: RKE2 etcd snapshot → Hetzner Volume mount
- [ ] `infrastructure/environments/dev/backup.tf`: backup jobs
- [ ] Restore runbook: `docs/disaster-recovery.md`
- [ ] RPO hedefi: 1 saat, RTO hedefi: 30 dakika

**S10-04: HA API + Zero-Downtime Deploy** *(2 gün)*
- [ ] API deployment: `replicas: 3`, PodDisruptionBudget (`minAvailable: 2`)
- [ ] Rolling update: `maxSurge: 1`, `maxUnavailable: 0`
- [ ] Liveness/readiness probes: `/health` endpoint
- [ ] Horizontal Pod Autoscaler: CPU %70 → scale out (max 10)
- [ ] API session affinity: `sessionAffinity: None` (stateless JWT)
- [ ] DB connection pool: `asyncpg` pool (`min_size=5, max_size=20`)

**S10-05: Security Hardening** *(2 gün)*
- [ ] Pod Security Standards: `restricted` profile (tenant namespaces), `baseline` (platform)
- [ ] Network Policies: CiliumNetworkPolicy per-tenant (egress kuralları, cross-namespace engel)
- [ ] RBAC audit: `kubectl auth can-i --list` ile minimal permission doğrulama
- [ ] Image scanning: Harbor Trivy — kritik CVE varsa build başarısız say
- [ ] Trivy severity threshold: CRITICAL → block, HIGH → warn
- [ ] Container image: non-root user (`USER 1000`), read-only root filesystem
- [ ] Secret rotation: `WEBHOOK_SECRET` ve `SECRET_KEY` için 90 günlük rotation CronJob

**S10-06: Performance + Caching** *(2 gün)*
- [ ] BuildKit cache: `--export-cache type=registry,ref={harbor}/buildcache/{app}` → Harbor
- [ ] API response cache: Redis (mevcut) için `fastapi-cache2` entegrasyonu
  - `/health/cluster` → 30 sn cache
  - Tenant listesi → 5 sn cache (sonra invalidate)
- [ ] DB query optimization: composite index ekle (`tenant_id + status`, `application_id + created_at`)
- [ ] Connection pool tuning: Prometheus metrics ile pool saturation izle
- [ ] CDN: UI static assets → Cloudflare (optional, Sprint 10 son)

### Test + CI/CD

**S10-07: Kapsamlı Test Suite** *(3 gün)*
- [ ] Unit tests: %80 coverage hedefi
- [ ] Integration tests: gerçek DB (test container), mock K8s (kind)
- [ ] E2E tests: Playwright (tenant oluştur → app deploy → URL doğrula)
- [ ] Load test: Locust veya k6 (100 concurrent user, build trigger storm)
- [ ] Security test: OWASP ZAP passive scan CI'a entegre
- [ ] CI/CD: GitHub Actions
  - `on: pull_request`: lint + unit test + build
  - `on: push main`: integration test + build + push Harbor + ArgoCD sync

**S10-08: Developer Experience** *(2 gün)*
- [ ] `Makefile`: `make dev`, `make test`, `make lint`, `make build`, `make deploy`
- [ ] Docker Compose: tam local stack (FastAPI + Next.js + PostgreSQL + Redis + Keycloak)
- [ ] `docs/getting-started.md`: 15 dakikada local dev setup
- [ ] API OpenAPI docs: Swagger UI → `/api/docs` (JWT auth butonu ile)
- [ ] Postman collection export: tüm endpoint'ler örnek request/response ile
- [ ] Changelog otomasyonu: `conventional-changelog` (conventional commits → CHANGELOG.md)

---

## Sprint 11 — Gelişmiş Platform Özellikleri
**Süre**: 2 hafta
**Öncelik**: 🟢 Düşük-Orta (post-production)

**S11-01: One-Click Rollback** *(2 gün)*
- [ ] Deployment history: son 10 deploy listesi (commit SHA, tarih, kim deploy etti, durum)
- [ ] `POST /tenants/{slug}/apps/{app_slug}/deployments/{id}/rollback`
- [ ] Rollback: mevcut `image_tag`'ı eski `image_tag`'a döndür (Deployment patch)
- [ ] K8s rollout undo: `kubectl rollout undo deployment/{name}`
- [ ] UI: deployment listesinde her satırda "Rollback to this" butonu

**S11-02: Canary Deploy** *(3 gün)*
- [ ] Cilium Gateway API traffic splitting: `%90 stable + %10 canary`
- [ ] `Application.canary_enabled`: canary mode aç/kapat
- [ ] `Application.canary_weight`: 0-100 slider
- [ ] Canary metrics: canary vs stable error rate karşılaştırma
- [ ] Auto-promote: canary error rate < stable → otomatik %100'e çek (konfig edilebilir)
- [ ] Auto-rollback: canary error rate > threshold → otomatik kapat

**S11-03: Cron Jobs** *(2 gün)*
- [ ] `CronJob` K8s resource desteği (app türü olarak)
- [ ] `Application.type`: `web` | `worker` | `cronjob`
- [ ] CronJob schedule: cron expression input (`0 * * * *`)
- [ ] CronJob history: son 5 run, stdout log, exit code
- [ ] CronJob UI: schedule badge, "Run Now" butonu, history tablosu

**S11-04: Private Registry Desteği** *(1 gün)*
- [ ] Harici Docker Hub / GHCR / ECR registry'den image pull
- [ ] `Application.image_source`: `git_build` | `external_image`
- [ ] `Application.external_image`: `ghcr.io/owner/repo:tag`
- [ ] Registry credentials: K8s imagePullSecret, per-tenant sakla

**S11-05: Persistent Storage (Volume Desteği)** *(2 gün)*
- [ ] `Application.volumes` JSON array: `[{name, mount_path, size_gi}]`
- [ ] PVC oluştur: Longhorn RWO, uygulama ile aynı lifecycle
- [ ] Deployment volumeMount inject
- [ ] Volume UI: "Add Volume" butonu, mount path + size input
- [ ] Volume listesi: kullanılan/toplam boyut

---

## Sprint 12 — Multi-Cluster + Multi-Region (Gelecek)
**Süre**: 4 hafta
**Öncelik**: 🟢 Düşük (Phase 2+)

**S12-01: Multi-Cluster Yönetimi**
- [ ] Rancher → Palette geçişi (Yahya partnership)
- [ ] Cluster API: provider abstraction (Hetzner + Cyso + AWS + Azure)
- [ ] Tenant → Cluster placement rules (region affinity, data residency)
- [ ] Cluster health dashboard: tüm cluster'lar tek panel

**S12-02: EU Multi-Region Deploy**
- [ ] Amsterdam (Cyso/Leafcloud) — Production NL
- [ ] Frankfurt (Hetzner FSN) — Dev/Staging
- [ ] Active-Active: Cilium Cluster Mesh veya Submariner (cross-cluster service discovery)
- [ ] Geo-routing: Cloudflare Load Balancing → en yakın region

**S12-03: White-Label Platform**
- [ ] `Platform.branding`: logo, primary color, custom domain
- [ ] Keycloak theme: `haven-{platform_name}` realm theme
- [ ] Email şablonları: müşteri logosu ile
- [ ] "Powered by Haven" toggle (enterprise'da kaldırılabilir)

---

## Bağımlılık Haritası (Özet)

| Sprint | Bağımlı Olduğu |
|--------|---------------|
| Sprint 0 | — (başlangıç) |
| Sprint 1 | Sprint 0 |
| Sprint 2 | Sprint 0 |
| Sprint 3 | Sprint 0 |
| Sprint 4 | Sprint 0 |
| Sprint 5 | Sprint 1, Sprint 3 |
| Sprint 6 | Sprint 0 |
| Sprint 7 | Sprint 4 |
| Sprint 8 | Sprint 2, Sprint 7 |
| Sprint 9 | Sprint 7 |
| Sprint 10 | Sprint 0-9 |
| Sprint 11 | Sprint 10 |
| Sprint 12 | Sprint 10 |

## Paralel Yürütülebilen Sprintler

```
Hafta 1-2:   Sprint 0 (tüm ekip)
Hafta 3-4:   Sprint 1 + Sprint 2 (paralel, farklı kişiler)
Hafta 5:     Sprint 3 + Sprint 4 (paralel)
Hafta 6-7:   Sprint 5 + Sprint 6 (paralel)
Hafta 8-9:   Sprint 7 + Sprint 8 hazırlık (paralel)
Hafta 10:    Sprint 8
Hafta 11:    Sprint 9
Hafta 12-14: Sprint 10 (production hardening, en uzun sprint)
Hafta 15-16: Sprint 11
Hafta 17+:   Sprint 12
```

---

## Outplane.com Parite Kontrol Listesi

| Outplane Özelliği | Bizim Durumumuz | Sprint |
|-------------------|-----------------|--------|
| Git push deploy | ✅ Çalışıyor | — |
| Auto build detection | ✅ Nixpacks | — |
| Private registry | ✅ Harbor | — |
| Custom domains | 🟡 Kısmi | Sprint 6 |
| Auto TLS | 🟡 Cert-manager var, wildcard eksik | Sprint 6 |
| Preview environments | ❌ Yok | Sprint 5 |
| Managed PostgreSQL | ✅ CNPG | — |
| Managed MySQL | ❌ Operator yok | Sprint 1 |
| Managed MongoDB | ❌ Operator yok | Sprint 1 |
| Managed Redis | 🟡 Kod var, doğrulanmamış | Sprint 1 |
| Managed RabbitMQ | 🟡 Kod var, doğrulanmamış | Sprint 1 |
| Service → App bağlantı | 🟡 Backend var, UI eksik | Sprint 1 |
| Real-time build logs | ✅ SSE streaming | — |
| Rollback | ❌ Yok | Sprint 11 |
| Horizontal autoscaling | ✅ HPA | — |
| Persistent storage | ❌ Yok | Sprint 11 |
| Cron jobs | ❌ Yok | Sprint 11 |
| Worker processes | ❌ Yok | Sprint 11 |
| Team collaboration | ❌ Yok | Sprint 4 |
| SSO/SAML | ❌ Yok | Sprint 7 |
| Usage billing | ❌ Yok | Sprint 8 |
| Audit logs | ❌ Yok | Sprint 7-9 |
| Real metrics (CPU/RAM) | ❌ Mock | Sprint 2 |
| Log aggregation | ❌ Mock | Sprint 2 |
| Distributed tracing | ❌ Yok | Sprint 2 |
| Canary deploy | ❌ Yok | Sprint 11 |
| GDPR compliance | ❌ Yok | Sprint 9 |
| Multi-region | ❌ Yok | Sprint 12 |
| Multi-cluster | ❌ Yok | Sprint 12 |

---

## Kritik Yol (MVP → Production)

**Minimum Viable Production (Sprint 0 + 1 + 6 + 10 subset):**
1. ✅ Sprint 0: Güvenlik düzeltmeleri + temel testler
2. ✅ Sprint 1: Managed services tamamla
3. ✅ Sprint 6: Custom domain + TLS
4. ✅ Sprint 10 subset: Backup, HA API, security hardening, production cluster

Bu 4 sprint tamamlandığında pilot müşteri (tek belediye) için production kullanım mümkün.

**Full Enterprise (tüm sprint'ler):** ~17 hafta

---

*Son güncelleme: 2026-03-28*
*Durum: Plan hazır, Sprint 0 başlıyor*
