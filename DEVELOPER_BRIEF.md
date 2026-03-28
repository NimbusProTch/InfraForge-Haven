# Haven Platform — Developer Brief

> **Hedef kitle**: Full-stack developer (Enes) — backend, DB, migration, test ve frontend
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
| Database | **PostgreSQL** (CloudNativePG) — async SQLAlchemy 2.0 |
| Migrations | **Alembic** (0001→0014 zinciri) |
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
│   │   ├── deps.py           # DBSession, CurrentUser, K8sDep
│   │   └── k8s/              # Kubernetes client wrapper
│   ├── alembic/
│   │   └── versions/         # 0001_initial_schema → 0014_add_clusters
│   └── tests/                # pytest, 274+ test
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

## D. Görevler (Öncelik Sırasıyla)

Her görev için hangi katmanların tamamlanması gerektiği belirtilmiştir.

### 1. Service → App Bağlantı UI ⭐⭐⭐ (Kritik)

| Katman | Durum |
|--------|-------|
| Backend endpoint | ✅ Hazır |
| DB model | ✅ Hazır (`Application.env_from_secrets`) |
| Migration | ✅ Hazır |
| Tests | ✅ Hazır (`test_service_connect.py`) |
| **Frontend** | ❌ Yapılacak |

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

| Katman | Durum |
|--------|-------|
| Backend endpoint | ✅ Hazır |
| DB model | ✅ Hazır (`ManagedService.secret_name`, `.connection_hint`) |
| Migration | ✅ Hazır |
| Tests | ✅ Hazır (`test_service_connect.py`) |
| **Frontend** | ❌ Yapılacak |

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

| Katman | Durum |
|--------|-------|
| Backend endpoint | ✅ Hazır (`routers/members.py`) |
| DB model | ✅ Hazır (`TenantMember`, roller: owner/admin/member/viewer) |
| Migration | ✅ Hazır (0007_add_tenant_members) |
| Tests | ⚠️ Eksik — test_members.py yok, yaz |
| **Frontend** | ❌ Yapılacak |

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
│ user@gemeente.nl       owner    [·]          │
│ dev1@gemeente.nl       member   [·]          │
│ viewer@gemeente.nl     viewer   [·]          │
└─────────────────────────────────────────────┘
```

**Kabul Kriterleri**:
- Invite modal: email input + rol seçimi (owner/admin/member/viewer)
- Rol dropdown ile inline değiştirme
- Üye çıkarma → confirm dialog
- Kendi kendini çıkaramaz (self-remove disabled)
- Son owner'ı çıkaramaz / downgrade edemezsin (backend 409 döner)

---

### 4. Environment Switcher ⭐⭐ (Önemli)

| Katman | Durum |
|--------|-------|
| Backend endpoint | ✅ Hazır (`routers/environments.py`) |
| DB model | ✅ Hazır (`Environment`) |
| Migration | ✅ Hazır (0008_add_environments) |
| Tests | ✅ Hazır (`test_environments.py`) |
| **Frontend** | ❌ Yapılacak |

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

| Katman | Durum |
|--------|-------|
| Backend endpoint | ✅ Hazır (`routers/audit.py`) |
| DB model | ✅ Hazır (`AuditLog`) |
| Migration | ✅ Hazır (0009_add_audit_logs) |
| Tests | ✅ Hazır (`test_audit.py`) |
| **Frontend** | ❌ Yapılacak |

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

| Katman | Durum |
|--------|-------|
| Backend endpoint | ✅ Hazır (`routers/billing.py`) |
| DB model | ✅ Hazır (`UsageRecord`) |
| Migration | ✅ Hazır (0010_add_billing) |
| Tests | ✅ Hazır (`test_billing.py`) |
| **Frontend** | ❌ Yapılacak |

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

| Katman | Durum |
|--------|-------|
| Backend endpoint | ✅ Hazır (`routers/organizations.py`) |
| DB model | ✅ Hazır (`Organization`, `OrganizationMember`, `SSOConfig`) |
| Migration | ✅ Hazır (0012_add_organizations_sso) |
| Tests | ✅ Hazır (`test_organizations.py`) |
| **Frontend** | ❌ Yapılacak |

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

### 8. Webhook URL Gösterimi

| Katman | Durum |
|--------|-------|
| Backend endpoint | ✅ Hazır (`routers/webhooks.py`) |
| DB model | ✅ Hazır (`Application.webhook_token`) |
| Migration | ✅ Hazır (0003_add_webhook_token) |
| **Frontend** | ❌ Yapılacak |

App detay → Settings tab'ında webhook URL'i göster:
```
Webhook URL: https://api.haven.nl/api/v1/webhooks/github
Secret Token: [Copy]
```

---

### 9. GitHub Seamless OAuth Flow

| Katman | Durum |
|--------|-------|
| Backend | ✅ Hazır |
| **Frontend UX** | ⚠️ İyileştirilebilir |

OAuth callback sonrası tenant seçimine yönlendir (şu an `/tenants` genel listesi).
"Connect GitHub" butonu zaten bağlıysa devre dışı + "Connected ✓" göster.

---

## E. Backend Görevleri

Backend büyük ölçüde tamamlanmış. Kalan eksikler:

1. **`test_members.py` eksik** — `routers/members.py` kapsanmıyor. Yazılmalı (aşağıda pattern var).

2. **Keycloak Self-Service Signup** — `keycloak/haven-realm.json`'da registration enabled
   yapılmalı. Şu an sadece admin console üzerinden kullanıcı açılabiliyor.

3. **Tenant RBAC Enforcement** — `TenantMember` tablosu var, `CurrentUser` dependency aktif,
   ama tenant'a üyelik kontrolü endpoint'lerde yapılmıyor. Hangi user hangi tenant'a
   erişebilir kontrolü eklenecek.

4. **Observability Entegrasyonu** — Loki/Mimir/Tempo stub durumunda. Gerçek log aggregation
   ve metrics için Grafana data source entegrasyonu gerekli (Sprint 5).

---

## F. DB Katmanı

### Stack

- **PostgreSQL** (prod: CloudNativePG cluster `haven-platform`)
- **SQLAlchemy 2.0** async (`AsyncSession`, `mapped_column`, `DeclarativeBase`)
- **Alembic** migration zinciri

### Migration Zinciri

```
0001_initial_schema          ← Tenant, Application, Deployment, Domain
0002_add_managed_services    ← ManagedService
0003_add_webhook_token       ← Application.webhook_token
0004_add_monorepo_and_detection
0005_add_mysql_mongodb_service_types
0006_add_github_token_to_tenants
0007_add_tenant_members      ← TenantMember
0008_add_environments        ← Environment
0009_add_audit_logs          ← AuditLog
0010_add_billing             ← UsageRecord
0011_add_gdpr_models         ← DataRetentionPolicy, UserConsent
0012_add_organizations_sso   ← Organization, OrganizationMember, SSOConfig
0013_add_canary_apptype_volumes_cronjobs
0014_add_clusters            ← Cluster
```

### Mevcut Modeller ve İlişkiler

```
Tenant (1) ──< Application (many)
Tenant (1) ──< ManagedService (many)
Tenant (1) ──< TenantMember (many)
Tenant (1) ──< AuditLog (many)
Tenant (1) ──< UsageRecord (many)
Application (1) ──< Deployment (many)
Application (1) ──< Domain (many)
Application (1) ──< Environment (many)
Application (1) ──< CronJob (many)
Organization (1) ──< OrganizationMember (many)
Organization (1) ──< SSOConfig (many)
```

### DB Schema Değişikliği Nasıl Yapılır

**Adım 1** — Modeli değiştir ya da yeni model oluştur (`api/app/models/`):

```python
# api/app/models/my_model.py
import uuid
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class MyModel(Base, TimestampMixin):
    __tablename__ = "my_models"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    optional_field: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

**Adım 2** — `__init__.py`'ye import ekle (varsa):

```python
# api/app/models/__init__.py — gerekirse yeni modeli buraya ekle
```

**Adım 3** — Migration oluştur:

```bash
cd api
alembic revision --autogenerate -m "add_my_model"
# → alembic/versions/0015_add_my_model.py oluşur
# İçeriği kontrol et, gerekirse düzenle
alembic upgrade head
```

**Adım 4** — Schema oluşturma (test ortamı için gereksiz — conftest `create_all` kullanır):

```bash
# Test: pytest fixtures SQLite in-memory kullanır, migration gereksiz
# Dev: alembic upgrade head (yukarıda)
```

### Enum Gotcha

SQLAlchemy Enum ile Python StrEnum aynı değerleri kullanmalı:

```python
class MyStatus(StrEnum):
    active = "active"
    deleted = "deleted"

# Model'de values_callable ZORUNLU (DB lowercase, Python camelcase uyumsuzluğu):
status: Mapped[MyStatus] = mapped_column(
    Enum(MyStatus, values_callable=lambda e: [x.value for x in e]),
    default=MyStatus.active,
)
```

---

## G. API Endpoint Pattern

### Tam Router Örneği

`api/app/routers/members.py`'dan:

```python
"""Router docstring."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DBSession  # her router'da bunlar
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember
from app.schemas.tenant_member import TenantMemberResponse, TenantMemberInvite

router = APIRouter(prefix="/tenants/{tenant_slug}/members", tags=["members"])


# Ortak helper: 404 wrapper
async def _get_tenant_or_404(tenant_slug: str, db: DBSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


# GET list
@router.get("", response_model=list[TenantMemberResponse])
async def list_members(tenant_slug: str, db: DBSession, current_user: CurrentUser):
    tenant = await _get_tenant_or_404(tenant_slug, db)
    result = await db.execute(
        select(TenantMember).where(TenantMember.tenant_id == tenant.id)
    )
    return list(result.scalars().all())


# POST create
@router.post("", response_model=TenantMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(tenant_slug: str, body: TenantMemberInvite, db: DBSession, current_user: CurrentUser):
    tenant = await _get_tenant_or_404(tenant_slug, db)
    member = TenantMember(tenant_id=tenant.id, email=body.email, role=body.role)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


# DELETE
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(tenant_slug: str, user_id: str, db: DBSession, current_user: CurrentUser):
    tenant = await _get_tenant_or_404(tenant_slug, db)
    # ... fetch + delete
    await db.delete(member)
    await db.commit()
```

### Router'ı `main.py`'ye Kaydet

```python
# api/app/main.py
from app.routers import my_new_router
app.include_router(my_new_router.router, prefix="/api/v1")
```

### CurrentUser Pattern

```python
from app.deps import CurrentUser

@router.get("/me")
async def get_me(current_user: CurrentUser):
    # current_user = {"sub": "keycloak-user-id", "email": "user@x.nl", ...}
    user_id = current_user["sub"]
    user_email = current_user["email"]
```

### Pagination Pattern

```python
from fastapi import Query

@router.get("", response_model=PaginatedResponse[ItemSchema])
async def list_items(
    tenant_slug: str,
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * page_size
    count_result = await db.execute(select(func.count()).select_from(Item).where(...))
    total = count_result.scalar_one()
    result = await db.execute(select(Item).where(...).offset(offset).limit(page_size))
    return {"items": list(result.scalars()), "total": total, "page": page, "page_size": page_size}
```

### Error Handling

```python
# 404
raise HTTPException(status_code=404, detail="Resource not found")

# 409 Conflict
raise HTTPException(status_code=409, detail="Resource already exists")

# 503 Service unavailable (K8s down)
if not k8s.is_available():
    raise HTTPException(status_code=503, detail="Kubernetes unavailable")
```

---

## H. Test Pattern

### conftest.py Nasıl Çalışıyor

`api/tests/conftest.py` üç şeyi sağlar:

1. **`db_session`**: Her test için sıfır SQLite in-memory DB (`Base.metadata.create_all`).
2. **`mock_k8s`**: `K8sClient`'ın tüm sub-client'ları `MagicMock` (unavailable by default).
3. **`async_client`**: FastAPI `app` + DB override + K8s override + `verify_token` bypass.

`verify_token` override:
```python
app.dependency_overrides[verify_token] = lambda: {"sub": "test-user", "email": "test@haven.nl"}
```
Test'te auth yok — her istek `test-user` olarak geçer.

### Async Test Yazma

```python
# Dosya: api/tests/test_members.py
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tenant import Tenant

# pytest.ini / pyproject.toml'da asyncio_mode = "auto" — @pytest.mark.asyncio gerekmez


async def test_list_members_empty(async_client: AsyncClient, sample_tenant: Tenant):
    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/members")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_add_member(async_client: AsyncClient, sample_tenant: Tenant):
    resp = await async_client.post(
        f"/api/v1/tenants/{sample_tenant.slug}/members",
        json={"email": "dev@gemeente.nl", "role": "member"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "dev@gemeente.nl"
    assert data["role"] == "member"


async def test_add_duplicate_member_returns_409(async_client: AsyncClient, sample_tenant: Tenant):
    payload = {"email": "dup@gemeente.nl", "role": "viewer"}
    await async_client.post(f"/api/v1/tenants/{sample_tenant.slug}/members", json=payload)
    resp = await async_client.post(f"/api/v1/tenants/{sample_tenant.slug}/members", json=payload)
    assert resp.status_code == 409
```

### Mock K8s Nasıl Kullanılır

```python
# K8s unavailable (default mock_k8s):
async def test_credentials_503_when_k8s_down(async_client: AsyncClient, sample_tenant):
    resp = await async_client.get(f"/api/v1/tenants/{sample_tenant.slug}/services/my-pg/credentials")
    assert resp.status_code == 503

# K8s available ile özel mock:
@pytest.fixture
def mock_k8s_with_secret():
    import base64
    k8s = MagicMock(spec=K8sClient)
    k8s.is_available.return_value = True
    k8s.core_v1 = MagicMock()
    secret = MagicMock()
    secret.data = {"password": base64.b64encode(b"s3cr3t").decode()}
    k8s.core_v1.read_namespaced_secret.return_value = secret
    return k8s

@pytest_asyncio.fixture
async def client_with_k8s(db_session, mock_k8s_with_secret):
    app.dependency_overrides[get_db] = lambda: (yield db_session)  # async generator
    app.dependency_overrides[get_k8s] = lambda: mock_k8s_with_secret
    app.dependency_overrides[verify_token] = lambda: {"sub": "u1", "email": "u@x.nl"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

### Minimum Test Coverage Beklentisi

Her yeni router/endpoint için:
- [ ] Happy path (200/201/204)
- [ ] 404 (resource not found)
- [ ] 409 (conflict, varsa)
- [ ] Auth olmadan erişim → 401 (override kaldırarak test edilebilir)
- [ ] K8s unavailable → 503 (K8s kullanan endpoint'lerde)

```bash
cd api && python3 -m pytest -q    # tüm testler geçmeli
cd api && python3 -m ruff check app/ tests/  # lint temiz olmalı
```

---

## I. Coding Standards

### Python / FastAPI

```python
# Python 3.12+, type hints zorunlu
# Pydantic v2: model_validator, field_validator
# SQLAlchemy 2.0: mapped_column, DeclarativeBase, async session
# Ruff: linter + formatter (line-length = 120)

# Import sırası: stdlib → third-party → local
import uuid
from fastapi import HTTPException
from sqlalchemy.orm import Mapped
from app.models.base import Base
```

Ruff config (`pyproject.toml`'da):
```toml
[tool.ruff]
line-length = 120
[tool.ruff.lint]
select = ["E", "F", "I"]
```

### TypeScript / Next.js

```typescript
// TypeScript strict mode
// Tailwind CSS + shadcn/ui component'lerini extend et
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

### PR / Commit Kuralları

- Commit: conventional commits (`feat:`, `fix:`, `ui:`, `test:`, `db:`)
- PR gerekli değil, direkt `main`'e push
- Her PR/commit'te: `pytest` temiz + `ruff` temiz + TypeScript type-check geçmeli

```bash
# Tüm kontroller:
cd api && python3 -m pytest -q && python3 -m ruff check app/ tests/
cd ui && npx tsc --noEmit
```

---

## J. Ortam Kurulumu

```bash
# Backend
cd api
pip install -e ".[dev]"
# .env dosyası gerekli (api/app/config.py'ye bak)
# DATABASE_URL, KEYCLOAK_URL, KEYCLOAK_REALM, vb.

# Frontend
cd ui
npm install
# .env.local gerekli:
# NEXT_PUBLIC_API_URL=http://localhost:8000
# NEXTAUTH_URL=http://localhost:3000
# NEXTAUTH_SECRET=...

# Test
cd api && python3 -m pytest -q
cd api && python3 -m ruff check app/ tests/

# Migration (dev DB üzerinde)
cd api && alembic upgrade head
```

### Kilit Dosyalar

| Dosya | Amaç |
|-------|------|
| `api/app/main.py` | FastAPI app, tüm router kayıtları |
| `api/app/deps.py` | DBSession, CurrentUser, K8sDep tanımları |
| `api/app/routers/` | 20 router dosyası |
| `api/app/models/` | SQLAlchemy modelleri |
| `api/app/schemas/` | Pydantic v2 request/response şemaları |
| `api/alembic/versions/` | Migration zinciri (0001→0014) |
| `api/tests/conftest.py` | Test fixtures (db_session, mock_k8s, async_client) |
| `ui/lib/api.ts` | TypeScript API client (tek kaynak) |
| `ui/app/tenants/[slug]/page.tsx` | Ana tenant sayfası |
| `ui/app/tenants/[slug]/apps/[appSlug]/page.tsx` | Ana app sayfası |
| `CLAUDE.md` | Platform hafızası + gotchas |

---

## K. İletişim ve Sorular

- Kod yorumları İngilizce yaz
- CLAUDE.md ve bu brief Türkçe
- Sorular için: (projeyi yöneten kişiye sor)
