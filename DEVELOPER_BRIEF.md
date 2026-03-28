# Haven Platform — Developer Brief

> **Hedef kitle**: Frontend developer (Enes)
> **Tarih**: 2026-03-28
> **Branch**: `main` (tüm sprintler merge edildi)

---

## A. Platform Genel Bakış

Haven, Hollanda'daki 342 belediye için tasarlanmış Haven-Compliant Self-Service DevOps
platformudur. Vercel/Railway'e benzer ama tamamen on-prem, EU data sovereignty garantili ve
VNG Haven standardına (15/15 zorunlu check) uyumludur. Belediyeler kendi Kubernetes
cluster'larında uygulama deploy edebilir, managed PostgreSQL/Redis gibi servisler
oluşturabilir, GitHub'dan otomatik build/deploy tetikleyebilir ve tüm bunları web arayüzünden
self-service olarak yapabilir.

### Tech Stack

| Katman | Teknoloji |
|--------|-----------|
| Frontend | **Next.js 14** (App Router) + **shadcn/ui** + **Tailwind CSS** |
| Backend API | **FastAPI** (Python 3.12+) — async, 20 router, 60+ endpoint |
| Database | **PostgreSQL** (CloudNativePG) — async SQLAlchemy |
| K8s | **RKE2** + **Cilium** Gateway API (Hetzner dev cluster) |
| Auth | **Keycloak** 26 (OIDC) + **NextAuth** |
| GitOps | **ArgoCD** |
| Registry | **Harbor** |
| Build | **BuildKit** + **Nixpacks** |
| Storage | **Longhorn** (RWX) |

### Repo Yapısı

```
haven-platform/
├── api/                      # FastAPI backend
│   ├── app/
│   │   ├── routers/          # 20 router dosyası
│   │   ├── services/         # Business logic
│   │   ├── models/           # SQLAlchemy ORM
│   │   ├── schemas/          # Pydantic v2
│   │   └── k8s/              # Kubernetes client wrapper
│   └── tests/                # 274 test (pytest)
├── ui/                       # Next.js 14 frontend
│   ├── app/                  # App Router sayfaları
│   └── lib/api.ts            # Merkezi TypeScript API client
├── infrastructure/           # OpenTofu (IaC)
└── platform/                 # ArgoCD + Helm values
```

---

## B. Mevcut Durum

### Backend (API)

- **20 router**, 60+ endpoint: `applications`, `services`, `deployments`, `members`,
  `environments`, `domains`, `audit`, `billing`, `gdpr`, `organizations`, `backup`, `canary`,
  `cronjobs`, `pvcs`, `clusters`, `observability`, `github`, `health`, `tenants`, `webhooks`
- **Auth**: `CurrentUser` dependency tüm endpoint'lerde aktif (`verify_token` → Keycloak JWKS)
- **Testler**: 274 test passing (`pytest` + `ruff` temiz)
- **Yeni (bu commit)**: `POST /tenants/{slug}/apps/{app}/connect-service`,
  `DELETE …/connect-service/{service_name}`,
  `GET /tenants/{slug}/services/{name}/credentials`

### Frontend (UI)

Mevcut sayfalar (`ui/app/`):

| Sayfa | Path | Açıklama |
|-------|------|----------|
| Landing | `/` | Anasayfa |
| Login | `/auth/signin` | Keycloak redirect |
| Dashboard | `/dashboard` | Genel özet |
| Tenant Listesi | `/tenants` | Tüm tenantlar |
| Tenant Oluştur | `/tenants/new` | Yeni tenant formu |
| Tenant Detay | `/tenants/[slug]` | Tenant dashboard (apps, services, members) |
| App Oluştur | `/tenants/[slug]/apps/new` | Yeni uygulama |
| App Detay | `/tenants/[slug]/apps/[appSlug]` | Build, deploy, logs, settings |
| GitHub Callback | `/github/callback` | OAuth sonrası redirect |

`ui/lib/api.ts`: 19 API grubu, 70+ fonksiyon — tüm backend endpoint'leri kapsıyor.

### Altyapı

- RKE2 cluster (Hetzner Falkenstein + Nuremberg), Cilium CNI, Longhorn storage
- Cert-Manager (Let's Encrypt), Gateway API (Cilium)
- Keycloak 26, ArgoCD 7.7, Harbor, CloudNativePG, MinIO
- Tenant izolasyonu: namespace + CiliumNetworkPolicy + ResourceQuota + RBAC + Keycloak realm

---

## C. Müşteri Yolculuğu

Bir belediye IT yetkilisi platforma girip backend + database + frontend deploy etmek istiyor.

### Adım 1 — Login

| | |
|--|--|
| **UI sayfası** | `/auth/signin` |
| **API** | Keycloak OIDC (NextAuth) |
| **Durum** | ✅ Çalışıyor — NextAuth + Keycloak entegre |
| **Yapılacak** | Self-service signup akışı (şu an admin console üzerinden) |

### Adım 2 — Tenant Oluştur

| | |
|--|--|
| **UI sayfası** | `/tenants/new` → `/tenants/[slug]` |
| **API** | `POST /api/v1/tenants` |
| **Durum** | ✅ Çalışıyor — slug, namespace, Keycloak realm otomatik |
| **Yapılacak** | Tenant detay sayfasına üye yönetimi tab'ı ekle |

### Adım 3 — GitHub Bağla

| | |
|--|--|
| **UI sayfası** | `/tenants/[slug]` → GitHub connect butonu |
| **API** | `GET /api/v1/github/auth/url`, `POST /api/v1/github/connect/{slug}` |
| **Durum** | ✅ Çalışıyor — OAuth, repo listeleme, private repo desteği |
| **Yapılacak** | — |

### Adım 4 — Database Oluştur

| | |
|--|--|
| **UI sayfası** | `/tenants/[slug]` → Services tab |
| **API** | `POST /api/v1/tenants/{slug}/services` |
| **Durum** | ✅ Çalışıyor — PostgreSQL (CNPG), MySQL, MongoDB, Redis, RabbitMQ |
| **Yapılacak** | Credentials gösterimi (connection string kopyalama paneli) |

### Adım 5 — App Oluştur

| | |
|--|--|
| **UI sayfası** | `/tenants/[slug]/apps/new` |
| **API** | `POST /api/v1/tenants/{slug}/apps` |
| **Durum** | ✅ Çalışıyor — repo/branch seçimi, port, env vars, Nixpacks detection |
| **Yapılacak** | Monorepo dizin seçici (`build_context`, `dockerfile_path`) |

### Adım 6 — Database → App Bağla

| | |
|--|--|
| **UI sayfası** | App detay sayfası veya Service detay |
| **API** | `POST /api/v1/tenants/{slug}/apps/{app}/connect-service` ✅ **YENİ** |
| **Durum** | ✅ Backend hazır (bu commit), **UI henüz yok** |
| **Yapılacak** | Service detayında "Connect to App" butonu, otomatik envFrom inject |

### Adım 7 — Build & Deploy

| | |
|--|--|
| **UI sayfası** | `/tenants/[slug]/apps/[appSlug]` → Build tab |
| **API** | `POST …/build`, `POST …/deploy`, `GET …/deployments`, `GET …/logs` (SSE) |
| **Durum** | ✅ Çalışıyor — BuildKit 3-4 dk, Nixpacks auto-detect, step visualization |
| **Yapılacak** | — |

### Adım 8 — Custom Domain + TLS

| | |
|--|--|
| **UI sayfası** | App detay → Domains tab |
| **API** | `POST …/domains`, `POST …/domains/{domain}/verify`, `POST …/sync-cert` |
| **Durum** | ✅ Çalışıyor — DNS TXT doğrulama, cert-manager Let's Encrypt |
| **Yapılacak** | — |

### Adım 9 — Monitor

| | |
|--|--|
| **UI sayfası** | App detay → Pods/Events tab |
| **API** | `GET …/pods`, `GET …/events`, `GET …/logs` (SSE) |
| **Durum** | ⚠️ Pods/events çalışıyor, Grafana/Loki entegrasyonu yok (stub) |
| **Yapılacak** | Loki log viewer, Mimir metrics grafiği, Tempo tracing (Sprint 5) |

### Adım 10 — Scale

| | |
|--|--|
| **UI sayfası** | App detay → Settings tab |
| **API** | `PATCH …/apps/{app}` (min_replicas, max_replicas, cpu_threshold) |
| **Durum** | ✅ Çalışıyor — HPA otomatik, K8s native |
| **Yapılacak** | Settings tab'da HPA config UI |

### Adım 11 — CI/CD (Auto-deploy)

| | |
|--|--|
| **UI sayfası** | App detay → Settings → Webhook |
| **API** | `POST /api/v1/webhooks/github`, `PATCH …/apps/{app}` (auto_deploy) |
| **Durum** | ✅ Çalışıyor — GitHub push → otomatik build+deploy |
| **Yapılacak** | Webhook URL gösterimi UI'da |

### Adım 12 — Takım Davet

| | |
|--|--|
| **UI sayfası** | `/tenants/[slug]` → Members tab (YOK) |
| **API** | `POST /api/v1/tenants/{slug}/members`, `PATCH …/{userId}`, `DELETE …/{userId}` |
| **Durum** | ✅ Backend hazır, **UI henüz yok** |
| **Yapılacak** | Members tab implement et |

---

## D. UI Görevleri (Öncelik Sırasıyla)

### 1. Service → App Bağlantı UI ⭐⭐⭐ (Kritik)

**Ne**: Service detay sayfasında veya App detay sayfasında "Connect to App" butonu.
Butona basınca seçili app'e service secret'ı otomatik inject edilir (Kubernetes envFrom).

**API'ler** (`api.ts`'te hazır):
```typescript
api.services.connectToApp(tenantSlug, appSlug, serviceName, token)
// → POST /tenants/{slug}/apps/{app}/connect-service {service_name}
// → Returns: Application (env_from_secrets güncellenmiş)

api.services.disconnectFromApp(tenantSlug, appSlug, serviceName, token)
// → DELETE /tenants/{slug}/apps/{app}/connect-service/{serviceName}
// → Returns: 204
```

**UI Wireframe**:
```
Service Detay: my-pg (PostgreSQL · ready)
┌─────────────────────────────────────┐
│ Status: ● ready                     │
│ Tier: dev                           │
│ Connection Hint: postgresql://...   │
│                                     │
│ Connected Apps:                     │
│   ○ Seçili app yok                  │
│                                     │
│ [Select App ▼]  [Connect]           │
└─────────────────────────────────────┘
```

**Kabul Kriterleri**:
- Service `ready` olmayan durumlarda Connect butonu disabled + tooltip
- App listesi tenant'ın applarını gösterir
- Connect sonrası "Connected" badge gösterilir
- Disconnect butonu mevcut bağlantıyı kaldırır
- App detayında bağlı servisler listesi: `env_from_secrets` array'inden okunur

---

### 2. Connection String / Credentials Paneli ⭐⭐⭐ (Kritik)

**Ne**: Managed service oluşturulduktan/hazır olduktan sonra credentials ve connection string
gösterimi. Tek tıkla kopyalama + güvenli gösterim (şifre maskelenmiş, göster/gizle).

**API** (`api.ts`'te hazır):
```typescript
api.services.credentials(tenantSlug, serviceName, token)
// → GET /tenants/{slug}/services/{name}/credentials
// → Returns: {service_name, secret_name, connection_hint, credentials: {key: value}}
```

**UI Wireframe**:
```
Service: my-pg (PostgreSQL)
┌─────────────────────────────────────────────┐
│ Credentials                                 │
│ ─────────────────────────────────────────── │
│ username    myuser                    [Copy] │
│ password    ••••••••  [Show]          [Copy] │
│ host        my-pg-rw.tenant-x.svc    [Copy] │
│ port        5432                     [Copy] │
│ database    my_pg                    [Copy] │
│                                             │
│ Connection String:                          │
│ postgresql://myuser:••••@my-pg-rw...  [Copy]│
└─────────────────────────────────────────────┘
```

**Kabul Kriterleri**:
- Service `provisioning` iken "Still provisioning…" mesajı + spinner
- Service `ready` olunca credentials otomatik yüklenir (polling veya refetch)
- Şifreler maskelenmiş, toggle ile göster/gizle
- Her alan için ayrı Copy butonu (toast feedback)
- Connection string template: `type://user:pass@host:port/db`

---

### 3. Members UI ⭐⭐ (Önemli)

**Ne**: Tenant detay sayfasına "Members" tab'ı. Takım üyesi davet etme, rol atama (admin /
developer / viewer), çıkarma.

**API'ler** (`api.ts`'te hazır):
```typescript
api.members.list(tenantSlug, token)     // GET /tenants/{slug}/members
api.members.add(tenantSlug, {email, role}, token)   // POST
api.members.update(tenantSlug, userId, {role}, token) // PATCH
api.members.remove(tenantSlug, userId, token)  // DELETE
```

**UI Wireframe**:
```
Tenant: gemeente-amsterdam
[Apps] [Services] [Members] [Audit] [Settings]
                  ─ aktif tab ─
┌─────────────────────────────────────────────┐
│ Members (3)                    [+ Invite]   │
│ ─────────────────────────────────────────── │
│ user@gemeente.nl       admin    [·]          │
│ dev1@gemeente.nl       developer [·]         │
│ viewer@gemeente.nl     viewer   [·]          │
└─────────────────────────────────────────────┘
```

**Kabul Kriterleri**:
- Invite modal: email input + rol seçimi (admin/developer/viewer)
- Rol dropdown ile inline değiştirme
- Üye çıkarma → confirm dialog
- Kendi kendini çıkaramaz (self-remove disabled)

---

### 4. Environment Switcher ⭐⭐ (Önemli)

**Ne**: App detay sayfasında production/staging/preview environment seçimi.
Her environment ayrı URL, ayrı build/deploy akışı.

**API'ler** (`api.ts`'te hazır):
```typescript
api.environments.list(tenantSlug, appSlug, token)
api.environments.create(tenantSlug, appSlug, {name, type, branch}, token)
api.environments.update(tenantSlug, appSlug, envName, body, token)
api.environments.delete(tenantSlug, appSlug, envName, token)
```

**UI Wireframe**:
```
App: my-backend
[production ▼] ← dropdown switcher, sayfa başında

  Environments: production | + staging | + preview/main

Build / Deploy / Logs: seçili environment'a göre
```

**Kabul Kriterleri**:
- Environment dropdown URL'e yansır: `/apps/[slug]?env=staging`
- "New Environment" butonu: isim + tip (staging/preview) + branch seçimi
- Her environment'ın kendi deployment history'si
- Default: `production`

---

### 5. Audit Log Viewer ⭐ (Orta)

**Ne**: Tenant bazlı audit log sayfası. Kim ne zaman ne yaptı.

**API** (`api.ts`'te hazır):
```typescript
api.audit.list(tenantSlug, {page, page_size, action, resource_type}, token)
// → {items: AuditLog[], total, page, page_size}
```

**UI Wireframe**:
```
Audit Logs [Filter: action ▼] [resource_type ▼]
┌────────────────────────────────────────────────────┐
│ 2026-03-28 14:32  user@x.nl  app.deploy  my-backend│
│ 2026-03-28 14:10  user@x.nl  service.create  my-pg │
│ ...                                                 │
└────────────────────────────────────────────────────┘
[< 1 2 3 >]   Showing 1-20 of 143
```

**Kabul Kriterleri**:
- Sayfalama (20/sayfa)
- Action ve resource_type filtreleri
- Tarih sıralaması (en yeni önce)

---

### 6. Billing / Usage Dashboard ⭐ (Orta)

**Ne**: Tenant'ın kaynak kullanımını gösteren dashboard. CPU, RAM, storage, build dakikaları.
Plan bilgisi (free/starter/pro/enterprise) ve upgrade butonu.

**API** (`api.ts`'te hazır):
```typescript
api.billing.usage(tenantSlug, historyMonths, token)
// → {tier, limits, current_period, usage_pct, history}
api.billing.updateTier(tenantSlug, tier, token)
```

**UI Wireframe**:
```
Plan: Starter  [Upgrade ↑]

Usage This Month:
  CPU    ████░░░░░░  42%    2.1 / 5 cores
  RAM    ██████░░░░  63%    3.2 / 5 Gi
  Storage █░░░░░░░░░  10%    5 / 50 Gi
  Builds  ████░░░░░░  40%    20 / 50 min

[Last 3 months history chart]
```

**Kabul Kriterleri**:
- Progress bar + yüzde + absolute değer
- Plan tier badge (color-coded)
- Geçmiş kullanım grafiği (line chart, recharts veya shadcn chart)
- Upgrade modal (tier seçimi)

---

### 7. Organization Yönetimi ⭐ (Orta)

**Ne**: Birden fazla tenant'ı gruplayan organization CRUD. SSO konfigürasyonu (Keycloak OIDC
client). Org-level billing özeti.

**API'ler** (`api.ts`'te hazır — `api.organizations.*`):
- Org CRUD: `list`, `create`, `get`, `update`, `delete`
- Members: `listMembers`, `addMember`, `updateMember`, `removeMember`
- SSO: `listSSO`, `createSSO`, `updateSSO`, `deleteSSO`
- Tenants: `listTenants`, `bindTenant`, `unbindTenant`
- Billing: `billingSummary`

**Kabul Kriterleri**:
- `/organizations` sayfası: org listesi + oluştur
- Org detay: members, bound tenants, SSO configs, billing summary
- SSO modal: provider (Keycloak/OIDC/SAML), client_id, client_secret

---

## E. Backend Görevleri

Backend büyük ölçüde tamamlanmış. Kalan eksikler:

1. **Keycloak Self-Service Signup** — `keycloak/haven-realm.json`'da registration enabled
   yapılmalı. Şu an sadece admin console üzerinden kullanıcı açılabiliyor.

2. **Tenant RBAC Enforcement** — `TenantMember` tablosu var, `CurrentUser` dependency aktif,
   ama tenant'a üyelik kontrolü endpoint'lerde yapılmıyor. Hangi user hangi tenant'a
   erişebilir kontrolü eklenecek.

3. **Observability Entegrasyonu** — Loki/Mimir/Tempo stub durumunda. Gerçek log aggregation
   ve metrics için Grafana data source entegrasyonu gerekli (Sprint 5).

4. **Alembic Migrations** — Şu an `create_all` ile schema oluşturuluyor. Production'da
   Alembic migration'ları gerekli (pyproject.toml'da alembic bağımlılığı var).

---

## F. Coding Standards

### TypeScript

```typescript
// TypeScript strict mode
// Tailwind CSS class-variance-authority (cva) ile variant'lar
// shadcn/ui component'lerini extend et, sıfırdan yazma
// api.ts'teki tipleri import et, tekrar tanımlama
import { api, type ManagedService, type ServiceCredentials } from "@/lib/api"

// API error handling pattern:
try {
  const data = await api.services.credentials(tenantSlug, serviceName, token)
  setCredentials(data)
} catch (err) {
  toast.error(err instanceof Error ? err.message : "Bilinmeyen hata")
}

// Loading state:
const [loading, setLoading] = useState(false)
// ...
setLoading(true)
try { ... } finally { setLoading(false) }
```

### Bileşen Yapısı

```
ui/app/tenants/[slug]/
├── page.tsx              # Tenant detay (Apps + Services + Members + Audit tabs)
├── apps/
│   ├── new/page.tsx      # App oluştur
│   └── [appSlug]/page.tsx # App detay (Build + Deploy + Logs + Settings tabs)
└── services/
    └── [serviceName]/page.tsx  # Service detay (Credentials + Connected Apps)
```

### shadcn/ui Bileşenleri

Mevcut kullanılanlar: `Button`, `Card`, `Input`, `Label`, `Select`, `Badge`, `Tabs`,
`Dialog`, `Toast`, `Table`, `Separator`.

Yeni görevler için önerilen:
- Credentials paneli: `Card` + `Input` (readonly) + `Button` (copy)
- Members: `Table` + `Dialog` (invite modal)
- Billing: `Progress` + shadcn `Chart` (recharts wrapper)
- Audit: `Table` + `Select` (filter)

### Test Beklentisi

UI testleri zorunlu değil (küçük ekip), ama component'ler testlenebilir şekilde yazılmalı.
Backend değişiklik yaparsan pytest + ruff temiz olmalı:

```bash
cd api && python3 -m pytest -q    # 274+ passed
cd api && python3 -m ruff check app/ tests/
```

### API Pattern

```typescript
// api.ts'ten:
api.services.connectToApp(tenantSlug, appSlug, serviceName, token)
api.services.credentials(tenantSlug, serviceName, token)
api.members.list(tenantSlug, token)

// Server Actions veya Client Component'te useEffect kullan
// SSE (log streaming) için getLogsUrl() helper'ını kullan:
import { getLogsUrl } from "@/lib/api"
const url = getLogsUrl(tenantSlug, appSlug, token)
const es = new EventSource(url)
```

---

## G. Ortam Kurulumu

```bash
# Backend
cd api
pip install -e ".[dev]"
# .env dosyası gerekli (api/app/config.py'ye bak)

# Frontend
cd ui
npm install
# .env.local gerekli: NEXT_PUBLIC_API_URL=http://localhost:8000

# Test
cd api && python3 -m pytest -q
cd api && python3 -m ruff check app/ tests/
```

### Kilit Dosyalar

| Dosya | Amaç |
|-------|------|
| `api/app/main.py` | FastAPI app, tüm router kayıtları |
| `api/app/routers/` | 20 router dosyası |
| `ui/lib/api.ts` | TypeScript API client (tek kaynak) |
| `ui/app/tenants/[slug]/page.tsx` | Ana tenant sayfası |
| `ui/app/tenants/[slug]/apps/[appSlug]/page.tsx` | Ana app sayfası |
| `CLAUDE.md` | Platform hafızası + gotchas |

---

## H. İletişim ve Sorular

- Kod yorumları İngilizce yaz
- Commit: conventional commits (`feat:`, `fix:`, `ui:`)
- PR gerekli değil, direkt `main`'e push
- Sorular için: (projeyi yöneten kişiye sor)
