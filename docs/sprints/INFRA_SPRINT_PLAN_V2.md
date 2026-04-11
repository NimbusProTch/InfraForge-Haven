# Haven Platform — Infrastructure Sprint Plan V2

> **Kapsam**: GitOps pipeline, managed services, build UX.
> **Önceki plan**: [INFRA_SPRINT_PLAN.md](INFRA_SPRINT_PLAN.md)
> **Tarih**: 2026-03-28
> **Platform**: Hetzner Cloud · RKE2 v1.32.3 · Cilium 1.16 · ArgoCD 7.7.3 · Gitea

---

## Sprint I-1: Gitea / Forgejo Kurulumu

**Hedef**: Kendi kendine barındırılan Git sunucusu — tenant repo otomasyonu için temel.

### Task Listesi

**Infra**
- [ ] `charts/gitea/` Helm chart değerleri — Gitea 1.22+ (Forgejo fork tercih edilebilir, MIT)
- [ ] `infrastructure/environments/dev/main.tf` — `rancher2_app_v2.gitea` kaynağı ekle
- [ ] Kalıcı depolama: Longhorn 10Gi PVC (gitea-data)
- [ ] CNPG veritabanı kullanımı: `haven-platform` cluster'ına `gitea` DB ekle
- [ ] HTTPRoute: `gitea.<LB_IP>.sslip.io` → gitea Service (port 3000)
- [ ] SSH Service: NodePort 30022 veya LB secondary port (git clone SSH için)
- [ ] admin token: Gitea API token → K8s Secret `gitea-admin-token` (haven-system)

**Backend** (`api/app/`)
- [ ] `services/gitea.py` — Gitea HTTP API wrapper (repo oluştur, sil, fork, webhook)
- [ ] `routers/gitea.py` — `/internal/gitea/health` endpoint (infra health check)
- [ ] Config: `GITEA_URL`, `GITEA_ADMIN_TOKEN` env var'ları `config.py`'a ekle

**Test Beklentisi**
- `curl https://gitea.<IP>.sslip.io` → Gitea login sayfası (HTTP 200)
- `gitea.py` unit test: mock HTTP, repo create/delete round-trip
- K8s Secret `gitea-admin-token` var mı: `kubectl get secret -n haven-system gitea-admin-token`

**Etkilenen Dosyalar**
```
infrastructure/environments/dev/main.tf
charts/gitea/values.yaml
api/app/services/gitea.py
api/app/routers/gitea.py
api/app/config.py
```

**Tahmini Süre**: 2 gün

---

## Sprint I-2: GitOps Repo Yapısı

**Hedef**: `haven-gitops` repo'su otomasyonu — tenant/app oluşturulunca klasör + values.yaml üretilir.

### Task Listesi

**Backend**
- [ ] `services/gitops_scaffold.py` — repo scaffold logic:
  - Tenant oluştur → `gitops/tenants/{slug}/` dizini + `kustomization.yaml`
  - App oluştur → `gitops/tenants/{slug}/apps/{app-slug}/values.yaml`
  - App sil → directory remove + commit
  - Tenant sil → tüm dizini temizle
- [ ] Template engine: `Jinja2` ile `values.yaml.j2` template render
- [ ] `models/gitops_commit.py` — GitopsCommit model (pending/done/failed, tenant_id, app_id, sha)
- [ ] `routers/apps.py` → `POST /apps` handler'a `gitops_scaffold.create_app_values()` çağrısı ekle
- [ ] `routers/tenants.py` → tenant create/delete handler'lara scaffold çağrısı ekle

**Templates** (`api/app/templates/gitops/`)
- [ ] `app-values.yaml.j2` — image, port, replicas, env_vars, resources blokları
- [ ] `tenant-kustomization.yaml.j2` — app dizinlerini `resources` listesi olarak referansla
- [ ] `namespace.yaml.j2` — tenant namespace tanımı

**Test Beklentisi**
- Tenant oluştur → Gitea'da `haven-gitops` repo'sunda `tenants/{slug}/` dizini var mı
- App oluştur → `tenants/{slug}/apps/{app}/values.yaml` oluştu mu, geçerli YAML mı
- App sil → dosya silindi mi, commit oluştu mu

**Etkilenen Dosyalar**
```
api/app/services/gitops_scaffold.py
api/app/models/gitops_commit.py
api/app/templates/gitops/app-values.yaml.j2
api/app/templates/gitops/tenant-kustomization.yaml.j2
api/app/templates/gitops/namespace.yaml.j2
api/app/routers/apps.py
api/app/routers/tenants.py
```

**Tahmini Süre**: 3 gün

---

## Sprint I-3: Queue-Based Git Writer

**Hedef**: Tüm Git yazma işlemleri Redis kuyruğu üzerinden, tek worker ile sıralı — çakışmayı önler.

### Mimari

```
API Handler → Redis Queue (FIFO) → GitWriter Worker → Gitea API/pygit2
                                        ↑
                              Tek instance, sıralı, retry logic
```

### Task Listesi

**Infra**
- [ ] Redis Deployment haven-system namespace'inde (varsa redis-operator kullan)
- [ ] `REDIS_URL` env var → Haven API Deployment

**Backend**
- [ ] `services/git_queue.py` — Redis List tabanlı queue:
  - `enqueue(op: GitOp)` → `RPUSH haven:git:queue <json>`
  - `GitOp` dataclass: `op_type`, `tenant_slug`, `app_slug`, `payload`, `correlation_id`
- [ ] `workers/git_writer.py` — async worker (ayrı process/asyncio task):
  - `BLPOP haven:git:queue` (blocking pop, 5s timeout)
  - Op dispatch: `create_file`, `update_file`, `delete_file`, `delete_directory`
  - Retry: exponential backoff, max 3, DLQ (haven:git:dlq)
  - Heartbeat log her 60s
- [ ] `models/gitops_commit.py` → status field: `queued | processing | committed | failed`
- [ ] Worker startup: `api/main.py`'e asyncio background task olarak ekle
- [ ] Dead-letter queue monitor: `GET /internal/git-queue/stats` endpoint

**Test Beklentisi**
- 10 eş zamanlı app create → sıralı commit (Gitea log'da çakışma yok)
- Worker crash → restart sonrası DLQ mesajları işleniyor mu
- `GET /internal/git-queue/stats` → `{"queue_len": 0, "dlq_len": 0, "processed": N}`

**Etkilenen Dosyalar**
```
api/app/services/git_queue.py
api/app/workers/git_writer.py
api/app/models/gitops_commit.py
api/app/main.py
api/app/routers/internal.py
```

**Tahmini Süre**: 3 gün

---

## Sprint I-4: ApplicationSet per Tenant

**Hedef**: Her tenant için ArgoCD ApplicationSet — app-of-apps pattern, otomatik app dağıtımı.

### Task Listesi

**Infra / GitOps**
- [ ] `platform/argocd/app-of-apps.yaml` güncelle — tenant AppSet'leri yönetir
- [ ] `platform/argocd/templates/tenant-appset.yaml.j2` — ApplicationSet template:
  ```yaml
  spec.generators:
    - git:
        repoURL: http://gitea.../haven-gitops.git
        revision: main
        directories:
          - path: tenants/{{ tenant_slug }}/apps/*
  spec.template.spec.source.helm.valueFiles:
    - values.yaml
  ```
- [ ] ArgoCD project per tenant: `AppProject` ile tenant izolasyonu (sadece kendi namespace)

**Backend**
- [ ] `services/argocd.py` → `create_application_set(tenant_slug)` metodu ekle
- [ ] `services/argocd.py` → `delete_application_set(tenant_slug)` metodu ekle
- [ ] Tenant create handler → `argocd.create_application_set()` çağır
- [ ] Tenant delete handler → `argocd.delete_application_set()` + `gitops_scaffold.delete_tenant()` çağır

**Test Beklentisi**
- Yeni tenant oluştur → ArgoCD UI'da `appset-{slug}` görünüyor mu
- `haven-gitops` repo'suna app values.yaml push → ArgoCD otomatik sync ve K8s'de Deployment var mı
- Tenant sil → AppSet silindi mi, namespace temizlendi mi

**Etkilenen Dosyalar**
```
platform/argocd/app-of-apps.yaml
platform/argocd/templates/tenant-appset.yaml.j2
api/app/services/argocd.py
api/app/routers/tenants.py
```

**Tahmini Süre**: 2 gün

---

## Sprint I-5: API → GitOps Entegrasyonu

**Hedef**: Env var, replicas, port, image tag değişiklikleri UI'dan → values.yaml güncellemesi → ArgoCD sync.

### Task Listesi

**Backend**
- [ ] `services/gitops_values.py` — values.yaml okuma/yazma:
  - `get_values(tenant_slug, app_slug)` → parsed dict
  - `set_env_var(tenant_slug, app_slug, key, value)` → queue'ya UPDATE op
  - `set_replicas(tenant_slug, app_slug, replicas)` → queue
  - `set_resources(tenant_slug, app_slug, cpu_req, mem_req, cpu_lim, mem_lim)` → queue
  - `set_image_tag(tenant_slug, app_slug, tag)` → queue (build sonrası otomatik)
- [ ] `routers/apps.py` → `PATCH /apps/{id}/env-vars` endpoint
- [ ] `routers/apps.py` → `PATCH /apps/{id}/scaling` endpoint (replicas + resources)
- [ ] `routers/apps.py` → `GET /apps/{id}/config` endpoint (mevcut values)
- [ ] Build pipeline sonu → `gitops_values.set_image_tag()` çağrısı (yeni image push sonrası)

**Frontend** (`ui/`)
- [ ] `app/apps/[id]/config/page.tsx` — yeni Config tab:
  - Env var editor (key-value table, add/remove/edit satır)
  - Replicas slider (1-10)
  - Resource sliders (CPU 0.1-4 core, Memory 128Mi-8Gi)
  - Save butonu → PATCH endpoint
- [ ] `components/env-var-editor.tsx` — yeniden kullanılabilir env var bileşeni
- [ ] Sensitive env var toggle (UI'da `🔒` ikonu, backend'de Vault'a yönlendir — I-7'ye bağlı)

**Test Beklentisi**
- UI'dan env var ekle → `GET /apps/{id}/config` güncellenmiş mi
- values.yaml Gitea'da değişti mi
- ArgoCD sync sonrası K8s Deployment env var'ı taşıyor mu

**Etkilenen Dosyalar**
```
api/app/services/gitops_values.py
api/app/routers/apps.py
ui/app/apps/[id]/config/page.tsx
ui/components/env-var-editor.tsx
```

**Tahmini Süre**: 3 gün

---

## Sprint I-6: ArgoCD Sync API

**Hedef**: Manuel sync tetikle, deployment history gör, tek tıkla rollback.

### Task Listesi

**Backend**
- [ ] `services/argocd.py` genişlet:
  - `sync_app(tenant_slug, app_slug)` → ArgoCD API `POST /applications/{name}/sync`
  - `get_sync_status(tenant_slug, app_slug)` → `Synced/OutOfSync/Progressing/Degraded`
  - `get_history(tenant_slug, app_slug)` → revision listesi (id, commit_sha, deployed_at, status)
  - `rollback(tenant_slug, app_slug, revision_id)` → `POST /applications/{name}/rollback`
- [ ] `routers/apps.py`:
  - `POST /apps/{id}/sync` — sync tetikle
  - `GET /apps/{id}/sync-status` — anlık durum
  - `GET /apps/{id}/history` — deployment geçmişi
  - `POST /apps/{id}/rollback` — body: `{"revision_id": N}`

**Frontend**
- [ ] `app/apps/[id]/deployments/page.tsx` — Deployments tab:
  - Deployment history tablosu (revision, commit SHA, tarih, durum)
  - Her satırda "Rollback" butonu
  - Sync butonu + "OutOfSync" badge
- [ ] Anlık sync durumu: 3s polling veya SSE
- [ ] Rollback confirmation dialog

**Test Beklentisi**
- `POST /apps/{id}/sync` → ArgoCD'de sync başladı mı (`Progressing`)
- `GET /apps/{id}/history` → en az 1 revision dönüyor mu
- Rollback → K8s'de önceki image tag deploy edildi mi

**Etkilenen Dosyalar**
```
api/app/services/argocd.py
api/app/routers/apps.py
ui/app/apps/[id]/deployments/page.tsx
ui/components/sync-status-badge.tsx
```

**Tahmini Süre**: 2 gün

---

## Sprint I-7: Vault / External Secrets Operator

**Hedef**: Sensitive env var'lar (DB passwords, API keys) K8s Secret yerine Vault'ta — audit trail + rotation.

### Task Listesi

**Infra**
- [ ] HashiCorp Vault Helm kurulumu (haven-system, dev mode başlangıçta)
- [ ] External Secrets Operator (ESO) Helm kurulumu
- [ ] `SecretStore` CRD: Vault backend → ESO bağlantısı
- [ ] Vault AppRole auth: her tenant için ayrı policy (`tenant-{slug}-policy`)
- [ ] HTTPRoute: `vault.<LB_IP>.sslip.io` → Vault UI (8200)

**Backend**
- [ ] `services/vault.py` — Vault API wrapper:
  - `write_secret(tenant_slug, app_slug, key, value)` → `secret/tenants/{slug}/apps/{app}`
  - `read_secret(tenant_slug, app_slug, key)` → value
  - `delete_secret(tenant_slug, app_slug, key)`
- [ ] `services/external_secrets.py` — ESO CRD yazıcı:
  - `create_external_secret(tenant_slug, app_slug, keys)` → `ExternalSecret` manifest → K8s apply
- [ ] `routers/apps.py` → `PATCH /apps/{id}/env-vars` — sensitive flag varsa Vault'a yaz
- [ ] `routers/apps.py` → `POST /apps/{id}/env-vars/rotate` — Vault secret rotation trigger

**Frontend**
- [ ] `components/env-var-editor.tsx` → sensitive toggle (`🔒` switch) ekle
- [ ] Sensitive var'lar masked gösterilir (`****`), value edit Vault'a gider
- [ ] Rotation butonu: "Rotate Secret" → son rotasyon zamanı göster

**Test Beklentisi**
- Sensitive env var ekle → Vault UI'da `secret/tenants/{slug}/apps/{app}/{key}` var mı
- K8s Secret `externalsecret-{app}` Vault değerini yansıtıyor mu
- Rotation → K8s Secret güncellendi mi, Pod restart tetiklendi mi

**Etkilenen Dosyalar**
```
infrastructure/environments/dev/main.tf  (Vault + ESO)
api/app/services/vault.py
api/app/services/external_secrets.py
api/app/routers/apps.py
ui/components/env-var-editor.tsx
```

**Tahmini Süre**: 3 gün

---

## Sprint I-8: DB Helm Templates (Managed Services)

**Hedef**: One-click veritabanı provision — PostgreSQL, MySQL, MongoDB, Redis, RabbitMQ.

### Task Listesi

**Charts** (`charts/`)
- [ ] `charts/haven-pg/` — CNPG Cluster wrapper chart:
  - `values.yaml`: `instances`, `storage.size`, `backup.enabled`, `backup.s3Bucket`
  - `templates/cluster.yaml` — `Cluster` CRD
  - `templates/backup.yaml` — `ScheduledBackup` CRD (backup.enabled ise)
- [ ] `charts/haven-mysql/` — Percona XtraDB wrapper:
  - `values.yaml`: `replicas`, `storage.size`
  - `templates/pxc-cluster.yaml` — `PerconaXtraDBCluster` CRD
- [ ] `charts/haven-mongodb/` — Percona MongoDB wrapper
- [ ] `charts/haven-redis/` — Redis Operator `RedisCluster` CRD wrapper
- [ ] `charts/haven-rabbitmq/` — RabbitMQ Operator `RabbitmqCluster` CRD wrapper

**Backend**
- [ ] `models/managed_service.py` — `ManagedService` model (type, tenant_id, status, connection_secret)
- [ ] `services/managed_db.py` — DB provision logic:
  - `provision(tenant_slug, db_type, config)` → GitOps'a `haven-pg` Helm release values.yaml push
  - `deprovision(tenant_slug, db_type, name)` → GitOps'tan kaldır
  - `get_connection_string(tenant_slug, db_name)` → K8s Secret'tan oku
- [ ] `routers/services.py` — `/tenants/{id}/services` CRUD endpoint'leri
- [ ] Auto env injection: DB provision sonrası `DATABASE_URL` → app'in values.yaml'ına inject et

**Frontend**
- [ ] `app/tenants/[id]/services/page.tsx` — Services tab:
  - DB türü seç (PostgreSQL/MySQL/MongoDB/Redis/RabbitMQ)
  - Size konfigürasyonu (storage, replicas)
  - Provision / Deprovision butonu
  - Status badge (Provisioning/Running/Failed)
  - "Connect to app" → otomatik env inject dialog

**Test Beklentisi**
- PostgreSQL provision → CNPG Cluster Running (kubectl get cluster -n tenant-{slug})
- `get_connection_string()` → geçerli connection string dönüyor mu
- App'e connect → `DATABASE_URL` env var app Deployment'ında var mı

**Etkilenen Dosyalar**
```
charts/haven-pg/
charts/haven-mysql/
charts/haven-mongodb/
charts/haven-redis/
charts/haven-rabbitmq/
api/app/models/managed_service.py
api/app/services/managed_db.py
api/app/routers/services.py
ui/app/tenants/[id]/services/page.tsx
```

**Tahmini Süre**: 4 gün

---

## Sprint I-9: DB Backup → MinIO S3

**Hedef**: Scheduled backup, PITR, restore endpoint — MinIO bucket per tenant.

### Task Listesi

**Infra**
- [ ] MinIO bucket otomasyonu: tenant oluşturulunca `backups-{slug}` bucket oluştur (MinIO API)
- [ ] CNPG backup endpoint Secret: `s3://backups-{slug}/postgres/` → her tenant için ayrı credential
- [ ] `charts/haven-pg/templates/backup.yaml` — `ScheduledBackup` (günlük 02:00 UTC)
- [ ] `charts/haven-pg/templates/scheduled-backup.yaml` — WAL archiving (PITR için)

**Backend**
- [ ] `services/backup.py`:
  - `list_backups(tenant_slug, db_name)` → MinIO object list + CNPG Backup CRD listesi
  - `create_backup(tenant_slug, db_name)` → on-demand `Backup` CRD oluştur
  - `restore(tenant_slug, db_name, backup_id)` → yeni CNPG Cluster from backup
  - `get_restore_status(restore_id)` → Cluster status polling
- [ ] `routers/services.py` → backup CRUD endpoint'leri:
  - `GET /services/{id}/backups`
  - `POST /services/{id}/backups` (on-demand)
  - `POST /services/{id}/restore` — body: `{"backup_id": "...", "target_time": "..."}`

**Frontend**
- [ ] `app/tenants/[id]/services/[service-id]/backups/page.tsx`:
  - Backup listesi tablosu (id, tarih, boyut, durum)
  - "Backup Now" butonu
  - "Restore" butonu + PITR datetime picker
  - Restore progress gösterimi

**Test Beklentisi**
- Scheduled backup çalıştı → MinIO `backups-{slug}/postgres/` altında nesneler var mı
- On-demand backup → CNPG Backup object `Completed` statüsünde mi
- Restore → yeni cluster healthy mi, data intact mı

**Etkilenen Dosyalar**
```
charts/haven-pg/templates/backup.yaml
charts/haven-pg/templates/scheduled-backup.yaml
api/app/services/backup.py
api/app/routers/services.py
ui/app/tenants/[id]/services/[service-id]/backups/page.tsx
```

**Tahmini Süre**: 3 gün

---

## Sprint I-10: Build/Deploy Pipeline UX

**Hedef**: Enterprise kalitesinde build log deneyimi — renkli, anlık, timeout-aware, net fail state.

### Task Listesi

**Backend**
- [ ] `routers/builds.py` → `GET /builds/{id}/logs/stream` — SSE (Server-Sent Events) endpoint:
  - K8s Pod log'larını `watch=true` ile stream et
  - ANSI escape kodlarını JSON SSE event'e gömülü gönder (`{"line": "...", "ansi": true}`)
  - Build tamamlanınca `{"event": "done", "status": "success|failed"}` gönder
  - Timeout: 10 dakika hard limit, 2 dakika no-output timeout
- [ ] `services/build.py` → build aşamaları enum: `CLONE | DETECT | BUILD | PUSH | DEPLOY`
- [ ] `routers/builds.py` → `GET /builds/{id}/status` — adım detayları (başlangıç/bitiş zamanları)

**Frontend**
- [ ] `components/build-log-viewer.tsx` — SSE tabanlı log viewer:
  - `ansi-to-html` paketi ile ANSI renk dönüşümü
  - Otomatik scroll-to-bottom (kullanıcı scroll ederse durdur)
  - "Jump to bottom" FAB
  - Font: `font-mono`, arka plan: `#0d1117` (GitHub dark)
  - Satır numaraları opsiyonel toggle
- [ ] `components/pipeline-steps.tsx` güncelle:
  - Her adım: ikon (⏳/✅/❌), başlık, süre (örn. "Build: 47s")
  - Aktif adım: spinner animasyon
  - Failed adım: kırmızı border + hata mesajı satırı
- [ ] `app/builds/[id]/page.tsx`:
  - SSE bağlantısı kur, bağlantı koparsa 3s sonra reconnect
  - "Rebuild" butonu (sadece terminal state'de)
  - Build süresi sayacı (canlı, saniye bazında)
  - Timeout uyarısı: "Bu build beklenenden uzun sürüyor (>5dk)"

**Test Beklentisi**
- Build başlat → log satırları SSE üzerinden geliyor mu (curl ile test edilebilir)
- ANSI renkleri browser'da doğru render ediliyor mu
- Build timeout → UI'da net hata mesajı gösteriliyor mu
- Bağlantı kesilmesi → otomatik reconnect çalışıyor mu

**Etkilenen Dosyalar**
```
api/app/routers/builds.py
api/app/services/build.py
ui/components/build-log-viewer.tsx
ui/components/pipeline-steps.tsx
ui/app/builds/[id]/page.tsx
```

**Tahmini Süre**: 3 gün

---

## Özet Tablosu

| Sprint | Başlık | Süre | Bağımlılık |
|--------|--------|------|-----------|
| I-1 | Gitea kurulumu | 2 gün | — |
| I-2 | GitOps repo yapısı | 3 gün | I-1 |
| I-3 | Queue-based git writer | 3 gün | I-2 |
| I-4 | ApplicationSet per tenant | 2 gün | I-2 |
| I-5 | API → GitOps entegrasyonu | 3 gün | I-3, I-4 |
| I-6 | ArgoCD sync API | 2 gün | I-5 |
| I-7 | Vault / ESO | 3 gün | I-3 |
| I-8 | DB Helm templates | 4 gün | I-4 |
| I-9 | DB backup → MinIO | 3 gün | I-8 |
| I-10 | Build/Deploy UX | 3 gün | — |
| **Toplam** | | **28 gün** | |

## Kritik Yol

```
I-1 → I-2 → I-3 → I-5 → I-6
                ↘
          I-4 ──→ I-8 → I-9
I-7 (paralel, I-3 sonrası)
I-10 (paralel, herhangi bir aşamada)
```
