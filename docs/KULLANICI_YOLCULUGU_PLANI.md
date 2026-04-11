# Haven Platform — Kullanıcı Yolculuğu Analizi

> **Senaryo**: Bir müşteri (gemeente) Haven platformuna gelip 3-tier uygulama deploy etmek istiyor:
> Frontend (React/Next.js) + Backend API (Node.js/Python) + Database (PostgreSQL)
>
> **Referans**: Vercel/Netlify/Outplane benzeri ama on-prem, Haven standartlarında, EU data sovereignty.
>
> **Analiz Tarihi**: 2026-03-28
> **Main Branch**: `cb4c9aa` — Sprint 12 dahil tüm sprintler merge edildi.

---

## Özet Dashboard

| # | Adım | Durum | Tamamlanma | Kritik Sorun |
|---|------|--------|------------|--------------|
| 1 | Tenant Signup/Login (Keycloak) | 🔴 Kırık | %15 | Auth enforce edilmiyor |
| 2 | Tenant oluşturma | ✅ Çalışıyor | %95 | Keycloak realm non-blocking |
| 3 | GitHub repo bağlama | ✅ Çalışıyor | %100 | — |
| 4 | Backend app oluşturma (detection) | ✅ Çalışıyor | %90 | Monorepo kısmen |
| 5 | Database (managed PostgreSQL) | ✅ Çalışıyor | %80 | Sadece CNPG tam |
| 6 | Connection string inject | ✅ Çalışıyor | %100 | — |
| 7 | Frontend app (static/SSR) | ❌ Yok | %0 | Hiç implement edilmedi |
| 8 | Build tetikleme (BuildKit) | ✅ Çalışıyor | %100 | — |
| 9 | Deploy (K8s) | ✅ Çalışıyor | %100 | — |
| 10 | Custom domain + TLS | ✅ Çalışıyor | %100 | — |
| 11 | Monitoring (CPU/Memory/Logs) | ⚠️ Stub | %5 | Prometheus/Loki bağlı değil |
| 12 | Scaling (HPA) | ✅ Çalışıyor | %100 | — |
| 13 | CI/CD (auto-deploy on push) | ✅ Çalışıyor | %90 | PR preview kısmen |

---

## Adım 1: Tenant Signup/Login (Keycloak)

### Mevcut Durum: 🔴 KRİTİK SORUN
**Tamamlanma: %15**

#### Ne Var
- `api/app/auth/jwt.py`: RS256 JWKS doğrulama, token cache, `CurrentUser` dependency
- `api/app/deps.py`: `get_current_user()` fonksiyonu tanımlı
- `keycloak/haven-realm.json`: Realm config template
- `keycloak/setup-realm.sh`: Realm kurulum scripti
- `ui/app/api/auth/[...nextauth]/route.ts`: NextAuth endpoint
- `ui/app/auth/signin/page.tsx`: Login sayfası

#### 🔴 Kritik Eksik: Auth Enforce Edilmiyor
```python
# jwt.py'de tanımlı AMA HİÇBİR ROUTER'DA KULLANILMIYOR:
async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    ...

# Tüm router'larda bu şekilde (auth YOK):
@router.get("/tenants/")
async def list_tenants(db: AsyncSession = Depends(get_db)):
    ...

# Olması gereken:
@router.get("/tenants/")
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # BU EKSİK
):
    ...
```

**Sonuç**: Tüm API endpoint'leri internette authentication gerektirmeden çalışıyor. Tenant A, Tenant B'nin verilerini görebilir.

#### Ne Eksik
1. **Self-service signup**: Kullanıcı "Kayıt Ol" butonuna basıp Keycloak'ta hesap açamıyor. Sadece admin Keycloak konsolundan yapabiliyor.
2. **Auth enforce**: `get_current_user` dependency'si hiçbir router'da kullanılmıyor.
3. **Tenant-level RBAC**: Kim hangi tenanta erişebilir? Kontrol yok.
4. **UI ↔ API auth flow**: NextAuth token'ı API'ye Bearer olarak gönderme akışı implement edilmemiş.

#### Ne Yapılması Gerekiyor
1. Tüm tenant-scoped endpoint'lere `Depends(get_current_user)` ekle
2. Keycloak'ta self-service registration flow aktifleştir (realm config güncelle)
3. Tenant RBAC: `user_sub` → `tenant_slug` mapping (TenantMember tablosu var, kullan)
4. UI: NextAuth session'dan token al, API request'lerine ekle

---

## Adım 2: Tenant/Proje Oluşturma

### Mevcut Durum: ✅ ÇALIŞIYOR
**Tamamlanma: %95**

#### Ne Var
- `POST /api/v1/tenants/`: Tenant oluşturur
- `api/app/services/tenant_service.py`: Tam K8s provision akışı

#### Gerçekten Oluşturulanlar (K8s)
```yaml
Namespace: tenant-{slug}
  labels:
    haven.io/tenant: "{slug}"
    pod-security.kubernetes.io/enforce: "restricted"

ResourceQuota: tenant-{slug}-quota
  cpu_limit: "16"
  memory_limit: "32Gi"
  storage_limit: "100Gi"

LimitRange: tenant-{slug}-limits
  default request: 100m CPU, 128Mi Memory
  default limit: 500m CPU, 512Mi Memory

CiliumNetworkPolicy: tenant-{slug}-isolation
  # Sadece aynı namespace'den ingress izni

Role + RoleBinding: tenant-admin
  # K8s RBAC, Keycloak group: haven:tenant:{slug}:admin

Secret: harbor-registry
  # Private image pull credentials
```

#### UI Akışı
1. Dashboard → "Yeni Tenant" butonu → `/tenants/new`
2. Slug + Display name gir
3. Submit → API çağrısı → K8s provision
4. Redirect: `/tenants/{slug}` — tenant dashboard

#### Eksikler
- Keycloak realm oluşturma try/except'te → hata olursa tenant K8s'te var ama Keycloak'ta yok (sessiz hata)
- Tenant delete'de Keycloak realm silinmiyor (K8s namespace silinir)
- UI: Tenant oluşturma sırasında resource quota konfigürasyon yok

---

## Adım 3: GitHub Repo Bağlama

### Mevcut Durum: ✅ ÇALIŞIYOR
**Tamamlanma: %100**

#### OAuth Akışı
```
UI → GET /api/v1/github/auth/url?tenant_slug={slug}
   → GitHub OAuth sayfası (read:user, repo, read:org)
   → GitHub redirect → /github/callback?code=...&state=...
   → POST /api/v1/github/auth/callback
   → Token DB'de saklanır (Tenant.github_token)
```

#### Repo Listeleme
```
GET /api/v1/github/repos?tenant_slug={slug}
  → Kullanıcı repo'ları + Org repo'ları (deduplication)
  → Private repo'lar dahil
  → Sayfalama ile tüm repo'lar
```

#### Otomatik Tespit
```
GET /api/v1/github/repos/{owner}/{repo}/detect?tenant_slug={slug}
  → Dil: Python, Node.js, Go, Ruby, Rust
  → Framework: FastAPI, Django, Flask, Express, Next.js
  → Servis ihtiyacı: PostgreSQL, MySQL, MongoDB, Redis, RabbitMQ
  → Dockerfile var mı?
```

---

## Adım 4: Backend App Oluşturma (Detection)

### Mevcut Durum: ✅ ÇALIŞIYOR
**Tamamlanma: %90**

#### Tespit Edilen Şeyler
```python
# api/app/services/detection_service.py

# Dil tespiti (dosya varlığına göre):
- Python: requirements.txt, pyproject.toml, setup.py, Pipfile
- Node.js: package.json
- Go: go.mod
- Ruby: Gemfile
- Rust: Cargo.toml

# Framework tespiti (dependency parse):
- FastAPI, Django, Flask (requirements.txt parse)
- Express, Next.js (package.json parse)

# Servis ihtiyacı tespiti:
- PostgreSQL: psycopg2, asyncpg, SQLAlchemy, django.db, Prisma, TypeORM
- Redis: redis-py, ioredis, aioredis
- MongoDB: pymongo, mongoose
- RabbitMQ: pika, amqplib
```

#### App Oluşturma Endpoint'i
```
POST /api/v1/tenants/{slug}/apps/
{
  "name": "my-api",
  "repo_url": "https://github.com/org/repo",
  "branch": "main",
  "port": 8000,
  "dockerfile_path": null,  # opsiyonel
  "build_context": null     # opsiyonel
}
```

#### Eksikler
- Monorepo desteği kısmen: `dockerfile_path` ve `build_context` field'ları var AMA UI'da gösterilmiyor
- `GET /github/repos/{owner}/{repo}/tree` endpoint'i yok → repo içindeki dizinleri listeleyemiyoruz
- Next.js detection var ama SSR/static build ayrımı yok (Adım 7'ye bak)

---

## Adım 5: Database (Managed PostgreSQL via CNPG)

### Mevcut Durum: ✅ ÇALIŞIYOR (CNPG)
**Tamamlanma: %80**

#### CNPG Provision Akışı
```
POST /api/v1/tenants/{slug}/services/
{
  "name": "my-db",
  "service_type": "postgresql",
  "tier": "starter"  # dev | starter | pro
}

K8s'te oluşturulan:
  Cluster.postgresql.cnpg.io/v1
    name: my-db
    namespace: tenant-{slug}
    instances: 1 (dev) / 3 (pro)
    storage: 5Gi (dev) / 20Gi (pro)
    storageClass: longhorn

Otomatik oluşturulan secret:
  my-db-app → postgresql://my-db-app@my-db-rw.tenant-{slug}.svc:5432/my-db_db
```

#### Diğer Servisler (Scaffold Var, Operator Yok)
| Servis | Kod | Operator Deployed | Çalışıyor mu? |
|--------|-----|------------------|---------------|
| PostgreSQL | ✅ | ✅ (CNPG) | ✅ Evet |
| MySQL | ✅ | ❌ | ❌ |
| MongoDB | ✅ | ❌ | ❌ |
| Redis | ✅ | ❌ (OpsTree) | ❌ |
| RabbitMQ | ✅ | ❌ | ❌ |

#### Eksikler
- MySQL/MongoDB için Percona operator'ları cluster'a kurulumu gerekiyor
- Redis için Redis operator kurulumu gerekiyor
- Service status polling: CNPG cluster hazır olana kadar bekleme yok

---

## Adım 6: Backend'e DB Connection String Inject Etme

### Mevcut Durum: ✅ ÇALIŞIYOR
**Tamamlanma: %100**

#### Nasıl Çalışıyor
```python
# deploy_service.py

# CNPG secrets otomatik olarak env var olarak inject ediliyor:
env_from = [
    V1EnvFromSource(
        secret_ref=V1SecretEnvSource(name="my-db-app", optional=True)
    )
]
# Bu secret şu key'leri içeriyor:
# DATABASE_URL=postgresql://...
# host=my-db-rw.tenant-slug.svc
# port=5432
# user=my-db-app
# password=xxxxx
# dbname=my-db_db
```

#### Manuel Env Var Yönetimi
```
PATCH /api/v1/tenants/{slug}/apps/{app_slug}/env
{
  "key": "REDIS_URL",
  "value": "redis://my-redis:6379"
}
```

---

## Adım 7: Frontend App Oluşturma (Static / SSR)

### Mevcut Durum: ❌ IMPLEMENT EDİLMEDİ
**Tamamlanma: %0**

#### Şu Anki Sorun
Haven platformu tüm app'leri **backend servis** olarak ele alıyor:
- BuildKit ile Docker image build eder
- K8s Deployment olarak çalıştırır
- `PORT` env var bind eder

Bu yaklaşım **Next.js SSR** için çalışır (`next start`), ama:
- ❌ Static site build'i desteklemiyor (sadece build, serve yok)
- ❌ CDN distribution yok
- ❌ `next export` / `vite build` gibi static build output'u için S3/MinIO serve etme yok
- ⚠️ Next.js **SSR olarak** deploy edilebilir (`next start`) — containerize edilirse çalışır

#### Geçici Çözüm (Şu An)
Next.js SSR olarak çalışır:
```dockerfile
FROM node:18
WORKDIR /app
COPY . .
RUN npm ci && npm run build
EXPOSE 3000
CMD ["npm", "start"]
```
→ Platform bunu detect edip build/deploy yapabilir.

#### Ne Yapılması Gerekiyor (Full Static)
1. `AppType.STATIC` desteği → nixpacks ile build, static files S3/MinIO'ya yükle
2. Nginx/Caddy sidecar → static dosyalar serve et
3. CDN prefix → Cloudflare Workers veya K8s Nginx ingress

---

## Adım 8: Build Tetikleme (BuildKit Pipeline)

### Mevcut Durum: ✅ ÇALIŞIYOR
**Tamamlanma: %100**

#### Build Akışı (K8s Job)
```
POST /api/v1/tenants/{slug}/apps/{app_slug}/deploy
  ↓
K8s Job oluştur: haven-builds namespace
  ↓
Init Container 1: git-clone
  → git clone https://oauth2:{token}@github.com/org/repo.git
  → git checkout {commit_sha}
  ↓
Init Container 2: nixpacks (opsiyonel)
  → nixpacks build → Dockerfile.nixpacks oluştur
  → Fallback: start command tespit et
  → ARM64 binary desteği (aarch64-unknown-linux-musl)
  ↓
Main Container: buildctl (BuildKit)
  → buildctl --frontend dockerfile.v0
  → Harbor'a push: harbor.{domain}/haven-{slug}/{app}:{commit_sha}
  ↓
Deployment update: image tag güncelle
```

#### Log Streaming
```
GET /api/v1/tenants/{slug}/apps/{app_slug}/deployments/{deployment_id}/logs
  → K8s pod logs (git-clone + nixpacks + buildctl)
  → UI'da real-time streaming
```

---

## Adım 9: Deploy (K8s Deployment, Service, HTTPRoute)

### Mevcut Durum: ✅ ÇALIŞIYOR
**Tamamlanma: %100**

#### Oluşturulan K8s Kaynakları
```yaml
Deployment: {app-slug}
  namespace: tenant-{slug}
  image: harbor.{domain}/haven-{slug}/{app}:{sha}
  resources:
    requests: {cpu: "50m", memory: "64Mi"}
    limits: {cpu: "500m", memory: "512Mi"}
  envFrom:
    - secretRef: {service-secret-name}
  securityContext:
    runAsNonRoot: true
    allowPrivilegeEscalation: false

Service: {app-slug}
  type: ClusterIP
  port: {app.port}

HTTPRoute: {app-slug}  (Gateway API)
  parentRefs: haven-gateway
  hostnames: ["{app-slug}.{slug}.{platform_domain}"]
  rules:
    - backendRefs: {app-slug}:{port}

HorizontalPodAutoscaler: {app-slug}
  minReplicas: {app.min_replicas}
  maxReplicas: {app.max_replicas}
  cpuUtilization: {app.cpu_threshold}%
```

#### URL Formatı
```
https://{app-slug}.{tenant-slug}.46.225.42.2.sslip.io
```

---

## Adım 10: Custom Domain Bağlama (DNS + TLS)

### Mevcut Durum: ✅ ÇALIŞIYOR
**Tamamlanma: %100**

#### DNS Doğrulama Akışı
```
POST /api/v1/tenants/{slug}/apps/{app_slug}/domains/
  { "domain": "my-app.gemeente.nl" }
  ↓
Response: Doğrulama token'ı + DNS talimatları

Kullanıcı DNS'e ekler:
  TXT: _haven-verify.my-app.gemeente.nl → "haven-{random_token}"
  VEYA
  CNAME: my-app.gemeente.nl → {app-slug}.{slug}.sslip.io

POST /api/v1/tenants/{slug}/apps/{app_slug}/domains/{id}/verify
  ↓
dnspython ile DNS sorgu → TXT/CNAME kontrol
  ↓
Verified → cert-manager Certificate CRD oluştur → Let's Encrypt
  ↓
HTTPRoute güncelle → custom domain ekle
```

---

## Adım 11: Monitoring (CPU/Memory/Logs)

### Mevcut Durum: ⚠️ STUB — GERÇEK VERİ YOK
**Tamamlanma: %5**

#### Ne Çalışıyor (Gerçek Data)
- ✅ Pod listesi ve status (K8s API)
- ✅ K8s Event'leri (CrashLoopBackOff vs.)
- ✅ Build log streaming (BuildKit job pod logs)
- ✅ Deployment history

#### Ne Çalışmıyor (Mock/Stub)
- ❌ CPU/Memory metrikleri → Prometheus bağlantısı yok
- ❌ App log aggregation → Loki bağlantısı yok
- ❌ Request rate/latency → Envoy/Cilium metrics yok
- ❌ Distributed traces → Tempo bağlantısı yok

#### Mevcut API
```python
# observability.py — pod/event data gerçek, metrics stub:
GET /api/v1/tenants/{slug}/apps/{app_slug}/pods   ✅ Gerçek
GET /api/v1/tenants/{slug}/apps/{app_slug}/events ✅ Gerçek
GET /api/v1/tenants/{slug}/apps/{app_slug}/metrics ⚠️ Stub
GET /api/v1/tenants/{slug}/apps/{app_slug}/logs   ⚠️ Stub (Loki yok)
```

#### Ne Yapılması Gerekiyor
1. `ServiceMonitor` CRD → Prometheus scraping aktifleştir
2. Grafana API → metrics proxy endpoint'i yaz
3. Loki HTTP API → log streaming endpoint'i yaz
4. UI: Grafana embed veya custom chart (recharts/d3)

---

## Adım 12: Scaling (HPA, Replicas)

### Mevcut Durum: ✅ ÇALIŞIYOR
**Tamamlanma: %100**

#### Konfigürasyon (App Settings)
```
PATCH /api/v1/tenants/{slug}/apps/{app_slug}/
{
  "min_replicas": 2,
  "max_replicas": 10,
  "cpu_threshold": 60,
  "resource_cpu_limit": "1000m",
  "resource_memory_limit": "1Gi"
}
→ HPA + Deployment güncellenir
```

#### Manuel Scale
```
POST /api/v1/tenants/{slug}/apps/{app_slug}/scale
{ "replicas": 5 }
→ Deployment.spec.replicas güncellenir
```

---

## Adım 13: CI/CD (Auto-Deploy on Push)

### Mevcut Durum: ✅ ÇALIŞIYOR
**Tamamlanma: %90**

#### GitHub Webhook Kurulumu
```
# App oluştururken webhook token alınır:
GET /api/v1/tenants/{slug}/apps/{app_slug}/
→ { "webhook_token": "abc123..." }

# GitHub'da webhook URL:
https://api.{platform}/api/v1/webhooks/github/{webhook_token}
Secret: same token (HMAC-SHA256)
Events: Push, Pull Request
```

#### Push Event Akışı
```
GitHub push → POST /webhooks/github/{token}
  ↓ HMAC-SHA256 doğrula
  ↓ Branch filter (sadece main/configured branch)
  ↓ asyncio.create_task(run_pipeline(...))
  ↓ Response 202 hemen döner

Background: Build + Deploy
  ↓ Deployment record → PENDING
  ↓ BuildKit Job → BUILDING
  ↓ K8s Deploy update → DEPLOYING
  ↓ Ready → RUNNING
```

---

## Kritik Sorunlar ve Öncelik Sırası

### 🔴 P0: Hemen Çözülmeli (Güvenlik)

#### 1. Authentication Enforcement
**Problem**: Tüm API endpoint'leri publice açık.

**Çözüm** (her router'a):
```python
from app.deps import get_current_user

@router.get("/tenants/{slug}/apps/")
async def list_apps(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # EKLE
):
    # Tenant member kontrolü:
    member = await db.get(TenantMember, (current_user["sub"], tenant.id))
    if not member:
        raise HTTPException(403, "Access denied")
    ...
```

**Etki**: ~2 saat iş, tüm API korunur.

#### 2. Default Secret'lar Değiştir
```python
# config.py'de:
SECRET_KEY: str = "change-me-in-production"  # ❌
HARBOR_ADMIN_PASSWORD: str = "Harbor12345"   # ❌
```
→ `.env` dosyasından okutulacak şekilde değiştir.

---

### 🟠 P1: Sprint MVP için (1-2 Hafta)

#### 3. Monitoring: Prometheus + Loki Bağla
- `ServiceMonitor` CRD oluşturan bir helper yaz
- Grafana API proxy endpoint'i ekle (mevcut Grafana zaten cluster'da)
- Loki HTTP API ile log endpoint'ini doldur

#### 4. Frontend SSR Desteği Belgele
- Next.js / Nuxt.js uygulamaları SSR olarak deploy edilebilir
- Detection service'e `app_type: "frontend-ssr"` ekle
- PORT=3000 default yap (şu an 8000)

#### 5. Keycloak Self-Service Signup
- Keycloak realm config'de `registrationAllowed: true`
- UI'da "Kayıt Ol" flow'u ekle
- Email verification zorunlu yap

---

### 🟡 P2: Sonraki Sprint (2-4 Hafta)

#### 6. PR Preview Environments
- Sprint 5'te scaffold var, akış tamamlanmamış
- PR webhook → preview namespace → özel URL

#### 7. MySQL/MongoDB Operatörleri Deploy Et
- Percona XtraDB Cluster Operator → Helm chart
- Percona Server for MongoDB Operator → Helm chart

#### 8. Static Site Desteği
- `AppType.STATIC` ekle
- Nixpacks build → output MinIO'ya yükle
- Nginx sidecar → serve et
- CDN config

#### 9. Redis Operator Deploy Et
- OpsTree Redis Operator yerine Redis Enterprise Operator (daha production-ready)
- Sentinel/Cluster mode

#### 10. Env Var UI
- Şu an PATCH endpoint var ama UI'da env var editörü kısmen çalışıyor
- `EnvVarEditor.tsx` var, implement tamamlanmalı

---

## Gerçek Dünya 3-Tier Deployment Senaryosu

### Şu An Mümkün Olan Flow

```
1. Admin → Keycloak'ta tenant user oluştur (manual)
2. User login → Haven UI → Keycloak SSO
3. "Yeni Tenant" → gemeente-amsterdam → K8s provision (✅)
4. GitHub Connect → OAuth flow (✅)
5. "Yeni App" → Backend API (Node.js) seç (✅)
   → Repo: github.com/gemeente/city-api
   → Detection: Express.js, PostgreSQL ihtiyacı
6. "Managed Services" → PostgreSQL ekle (✅)
   → CNPG cluster → my-db-app secret
7. "Deploy" → Build tetikle (✅)
   → Nixpacks → Dockerfile → BuildKit → Harbor push
   → K8s Deployment + HTTPRoute
   → URL: city-api.amsterdam.46.225.42.2.sslip.io
8. Backend env var'a DB URL inject oldu (✅)
9. Custom domain: api.amsterdam.nl → DNS verify → TLS (✅)
10. Webhook: GitHub push → auto-deploy (✅)
11. Frontend app → Next.js SSR → ÇALIŞIR (konteyner olarak) (✅*)
    * Static export desteklenmiyor

SORUN: Auth enforce yok → güvenlik açığı
SORUN: Monitoring → sadece pod status, metrics yok
```

### Tam MVP için Kalan İş
1. **Auth enforce** → ~2-4 saat → tüm router'lar
2. **Monitoring proxy** → ~1-2 gün → Prometheus/Loki API bridge
3. **Keycloak signup** → ~1 gün → realm config + UI flow
4. **Frontend SSR dokümantasyon** → ~2 saat

**Sonuç**: 3-tier deployment şu an teknik olarak çalışıyor ama production'a göndermek için güvenlik enforcement şart.

---

## Dosya Referansları

| Konu | Dosya |
|------|-------|
| JWT Auth | `api/app/auth/jwt.py` |
| Auth dependency | `api/app/deps.py` |
| Tenant provision | `api/app/services/tenant_service.py` |
| Build pipeline | `api/app/services/build_service.py` |
| Deploy | `api/app/services/deploy_service.py` |
| Detection | `api/app/services/detection_service.py` |
| CNPG provision | `api/app/services/managed_service.py` |
| Custom domain | `api/app/services/domain_service.py` |
| GitHub OAuth | `api/app/routers/github.py` |
| Webhooks | `api/app/routers/webhooks.py` |
| Observability | `api/app/routers/observability.py` |
| Keycloak setup | `keycloak/setup-realm.sh` |
| Keycloak realm | `keycloak/haven-realm.json` |
| Haven chart | `charts/haven-app/` |
| Managed svc chart | `charts/haven-managed-service/` |
