# Haven Platform - Proje Hafızası

> Bu dosya Claude Code için proje hafızası görevi görür. Her session bu dosyayı okur.

## Proje Nedir?

Haven-Compliant Self-Service DevOps Platform (PaaS). Hollanda'daki 342 belediye için
VNG Haven standardına uygun Kubernetes altyapısı üzerine Heroku/Railway benzeri
self-service platform. EU data sovereignty garantili.

## Tech Stack

| Katman | Teknoloji |
|--------|-----------|
| IaC | **OpenTofu** (Terraform fork, CNCF) |
| Cluster Mgmt | **Rancher** (ücretsiz, multi-cluster) |
| K8s Dağıtımı | **RKE2** (CIS hardened, CNCF certified) |
| CNI | **Cilium** (eBPF, Gateway API, Hubble) |
| Ingress | **Cilium Gateway API** (Nginx yerine) |
| Storage | **Longhorn** (CNCF, RWX desteği) |
| TLS | **Cert-Manager + Let's Encrypt** |
| DNS | **Cloudflare + External-DNS** |
| Auth | **Keycloak** (realm-per-tenant) |
| GitOps | **ArgoCD** (platform servisleri için) |
| App Build | **Nixpacks + Kaniko** (K8s-native) |
| Registry | **Harbor** (self-hosted, Trivy scan) |
| Monitoring | **Grafana + Loki + Mimir + Hubble** |
| Backend | **Python 3.12+ / FastAPI** |
| Frontend | **Next.js 14+ / shadcn/ui** (Phase 2) |
| Dev Cloud | **Hetzner** (Falkenstein + Nuremberg) |
| Prod Cloud | **Cyso Cloud / Leafcloud** (Amsterdam, Phase 2+) |

## Repo Yapısı (Monorepo)

```
haven-platform/
├── CLAUDE.md                    # Bu dosya
├── infrastructure/              # OpenTofu
│   ├── modules/
│   │   ├── rancher-cluster/     # RKE2 cluster + Helm templates
│   │   │   ├── main.tf          # rancher2_cluster_v2 (Cilium CNI)
│   │   │   ├── variables.tf     # enable_hubble, replicas, etc.
│   │   │   ├── outputs.tf       # cluster_id, registration_token, rendered values
│   │   │   └── templates/       # Helm value templates (common)
│   │   │       ├── cilium-values.yaml.tpl
│   │   │       └── longhorn-values.yaml.tpl
│   │   ├── hetzner-infra/       # VM, Network, LB, Firewall
│   │   │   └── templates/
│   │   │       └── management-cloud-init.yaml.tpl
│   │   ├── openstack-infra/     # Cyso/Leafcloud (Phase 2+)
│   │   └── dns/                 # Cloudflare DNS
│   ├── environments/
│   │   ├── dev/                 # Hetzner dev cluster
│   │   │   ├── main.tf          # Module calls + nodes + app installs
│   │   │   ├── providers.tf     # Two rancher2 providers (bootstrap + admin)
│   │   │   ├── variables.tf     # All env variables
│   │   │   ├── outputs.tf
│   │   │   ├── versions.tf
│   │   │   ├── terraform.tfvars # Secrets (gitignored)
│   │   │   └── templates/
│   │   │       └── node-cloud-init.yaml.tpl  # Env-specific
│   │   └── production/          # Cyso/NL production
│   └── tenants/                 # Müşteri .tfvars dosyaları
├── platform/                    # ArgoCD + Helm
│   ├── argocd/
│   │   ├── app-of-apps.yaml
│   │   └── apps/               # Her servis için Application
│   ├── helm-values/            # Helm override'ları
│   ├── base/                   # Namespace, RBAC template
│   └── tenants/                # Tenant manifests (API oluşturur)
├── api/                        # Platform API (FastAPI)
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models/             # SQLAlchemy modelleri
│   │   ├── schemas/            # Pydantic v2
│   │   ├── routers/            # API endpoint'leri
│   │   ├── services/           # Business logic
│   │   ├── k8s/                # Kubernetes client wrapper
│   │   └── auth/               # Keycloak JWT
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── ui/                         # Portal (Next.js, Phase 2)
├── automation/                 # Claude Code runner + Telegram bot
├── ansible/                    # Dedicated DB (Phase 3)
└── docs/
```

## Mimari Kararlar

### IaC: Her Şey Kod
- UI sadece monitoring/dashboard. Oluşturma, güncelleme, silme = hep OpenTofu.
- `tofu apply -var-file="tenants/gemeente-utrecht.tfvars"` ile yeni müşteri.
- CI/CD: git push → tofu plan → tofu apply → ArgoCD sync → Haven check.

### IaC Pattern: Two-Provider + Module
- **rancher2.bootstrap**: İlk Rancher login (known password)
- **rancher2.admin**: Cluster operasyonları (token from bootstrap)
- **rancher-cluster module**: Cluster tanımı + Helm value template'leri (common)
- **Environment level**: Node'lar + `rancher2_app_v2` install'lar (enable/disable)
- **Helm templates**: Module'da (`modules/rancher-cluster/templates/`), env'de değil
- **cloud-init**: Node registration (env-specific, `environments/dev/templates/`)
- **Wait pattern**: `rancher2_cluster_sync` (native, Go-based, `wait_catalogs=true`, `state_confirm=3`)

### Rancher Management (Production-Grade)
- **K3s + Helm** (Docker yerine) - production-ready, HA-scalable
- Management node: K3s → cert-manager (Helm) → Rancher (Helm)
- Cloud-init runtime IP detection (Hetzner metadata API)
- `terraform_data.wait_for_rancher`: K3s + Helm boot ~10-15dk
- Tek node (dev), 3 node HA (prod) - scale edilebilir

### Multi-Tenancy: 5 Katmanlı İzolasyon
1. **Namespace**: `tenant-{name}` per tenant
2. **CiliumNetworkPolicy**: L7 izolasyon
3. **ResourceQuota**: CPU/RAM/Disk limitleri
4. **RBAC**: Tenant admin sadece kendi namespace'i
5. **Keycloak**: Tenant başına realm

### App Deploy Akışı (Phase 1)
1. GitHub repo → Detector (dil/framework tespit)
2. Kaniko pod → Nixpacks/Dockerfile → Harbor'a push
3. Deployer → Deployment + Service + HTTPRoute + HPA
4. Cert-Manager → otomatik TLS
5. GitHub webhook → auto-deploy

### Cluster Yönetimi
- Şimdi: **Rancher** (ücretsiz, yeterli)
- İleride: **Palette** (opsiyonel, Yahya partnership)

### MVP'de K8s API Direkt
- Müşteri app'leri: API → kubernetes Python client → K8s API
- Platform servisleri: ArgoCD ile GitOps
- Müşteri GitOps: Phase 3+ (internal Gitea)

## Konvansiyonlar

### Python / FastAPI
- **Python 3.12+**, type hints zorunlu
- **Pydantic v2** (model_validator, field_validator)
- **SQLAlchemy 2.0** async (mapped_column, DeclarativeBase)
- **Ruff** linter + formatter (line-length = 120)
- Import sırası: stdlib → third-party → local
- Router dosyaları: `routers/{resource}.py`
- Service dosyaları: `services/{domain}.py`
- Test dosyaları: `tests/test_{module}.py`

### OpenTofu / HCL
- Module yapısı: `modules/{provider}-{resource}/`
- Environment yapısı: `environments/{env}/`
- Değişkenler: `variables.tf`, çıktılar: `outputs.tf`
- Naming: `{resource_type}-{environment}-{purpose}`
- Helm templates: Module içinde (`templates/*.yaml.tpl`)
- State: remote backend (S3-compatible, Phase 0+)
- **rancher2 provider v5.x** → Rancher 2.9.x (Go-native, no bash)

### Git
- Branch: `feature/{phase}-{description}` veya `fix/{description}`
- Commit: conventional commits (feat:, fix:, infra:, docs:)
- Kod yorumları İngilizce, CLAUDE.md Türkçe
- Her task = 1 commit
- PR gerekli değil (küçük ekip), direkt main'e push

### Genel
- Dil: Türkçe (CLAUDE.md, dokümantasyon)
- Kod içi değişken/fonksiyon isimleri: İngilizce
- Kod yorumları: İngilizce
- Secret'lar: .env dosyası (git'e eklenmez), prod'da K8s Secret/Vault
- Para harcamamak için test bitince `tofu destroy`

## Haven Compliancy — GERÇEK SKOR: **13/15** (canlı doğrulanmış 2026-04-09 sabah)

> **Tarihçe**: Bu tablo bir zamanlar "15/15 ✅" diyordu ama 5-agent + 4-tur audit gerçek skoru `11.5/15` çıkardı. Sprint H0 → H4 ve sonraki devam round'larından sonra **şu an 13/15** — kalan 2 maddeden biri hâlâ tofu apply bekliyor (kod hazır, lokal tfvars'ta), diğeri yeni kod gerektiriyor.

| # | Check | Gerçek Durum (canlı doğrulanmış) | Status |
|---|-------|-------|--------|
| 1 | Multi-AZ | Cluster hâlâ `nbg1+hel1` (Helsinki). **Kod hazır**: `terraform.tfvars` `location_secondary = "fsn1"` yapıldı (lokal, gitignored). **Kalan iş**: operatör tarafından `tofu apply` (~60 dk node rebuild + 3 tenant eviction). | ⚠️ **KOD HAZIR, APPLY BEKLİYOR** |
| 2 | 3+ master, 3+ worker | 3 master + 3 worker, hepsi Ready (canlı verified) | ✅ |
| 3 | CNCF Conformance | RKE2 v1.32.3+rke2r1 — certified list'te | ✅ |
| 4 | kubectl access via OIDC | ❌ **HÂLÂ BROKEN**. RKE2 master cloud-init'te `--oidc-issuer-url` flag YOK. `keycloak/haven-realm.json`'da `groups` protocolMapper YOK. **Kalan iş (en karmaşık)**: 3 yerli kod fix + Keycloak realm reimport + master rolling restart. PR henüz yok. | ❌ **BROKEN** |
| 5 | RBAC | **DÜZELTİLDİ (#89 + #106)**. Rogue `haven-api-admin → cluster-admin` binding silindi. ClusterRole privilege escalation gap (clusterrolebindings full verbs) kapatıldı. `kubectl auth can-i '*' '*' --as=...haven-api` → **no** (canlı verified). | ✅ |
| 6 | CIS Hardening | `enable_cis_profile = true`, etcd taint tolerations eklendi | ✅ |
| 7 | CRI containerd | RKE2 default `containerd://2.0.4-k3s2` | ✅ |
| 8 | CNI Cilium + Hubble | Cilium 6 pod Running, Hubble enabled. **NOT**: WireGuard encryption kod-default `true` yapıldı (#112), tofu apply ile aktive olur. | ✅ (with caveat) |
| 9 | Separate master/worker | Distinct VM'ler, label'lar ayrı | ✅ |
| 10 | RWX Storage Longhorn | Default storage class, PVC'ler bağlı, RWX destek | ✅ |
| 11 | Auto-scaling HPA | metrics-server çalışıyor, HPA test edildi | ✅ |
| 12 | Auto HTTPS cert-manager | 14+ Certificate Ready=True, real Let's Encrypt | ✅ |
| 13 | Log aggregation Loki | loki-stack + 6 promtail node, log akıyor | ✅ |
| 14 | Metrics Prometheus + Grafana | Tüm pod'lar Running, ServiceMonitor scraping | ✅ |
| 15 | Image SHA digest | **DÜZELTİLDİ (#99 + #105)**. haven-api/haven-ui artık `@sha256:341a3844…` ve `@sha256:908f50b…` formatında deploy ediliyor. CI pipeline `docker/build-push-action@v6` digest output'unu yakalayıp deployment manifest'lerine yazıyor. (Canlı verified) | ✅ |

**Gerçek skor: 13/15 ✅ + 1 kod-hazır-apply-bekliyor + 1 kırık.** Sprint H1a-1 (Multi-AZ tofu apply) tamamlanırsa 14/15. Sprint H1a-2 (kubectl OIDC) tamamlanırsa 15/15.

**Bu sprint'te canlı cluster'a inen güvenlik katmanları** (önceden yoktu):
- JWT issuer doğrulaması (`verify_iss=True`) + JWKS TTL 1h cache (#86) + http/https scheme tolerance (#109/#110)
- Token revocation (per-user reauth watermark, alembic 0023) (#95)
- JWT `tenant_memberships` claim helpers (#96)
- `platform-admin` realm role + `require_platform_admin` dep (#92)
- 14 router'da `_get_tenant_or_404` → tek canonical `TenantMembership` dep (#90, #97, #100, #101, #102, #103)
- haven-api ClusterRole scope-down + privilege escalation gap kapatıldı (#89, #106)
- haven-api/ui image immutable digest pinning (#99, #105)
- haven-realm.json hardcoded credential temizliği (#91)
- kubectl OIDC integration (RKE2 + Keycloak haven-kubectl client + tenant_service group provisioning) (#108)
- BuildJob model + dead table silindi (#80)
- Static analysis baseline (bandit + vulture + xenon + mypy) + GitHub Security tab SARIF upload (#83, #84)
- Pre-commit hook (gitleaks + ruff format) (#85)
- **Sprint H1d (PSA / WireGuard / audit log)**: PSA `restricted` profile yeni tenant ns'lerinde aktif (#111); Cilium WireGuard kod-default `true` (#112, apply bekliyor); kube-apiserver audit policy file + flags kod-hazır (#113, apply bekliyor)
- **Sprint H1e (encryption / vault hibrit kapatma)**: Tenant deprovision orphan Everest sweep (#114); Harbor TLS externalURL https + BuildKit secure docker config (#115); MinIO server-side encryption KMS auto-encryption kod-hazır (#116, apply bekliyor + key gen); Vault → ESO migration plan + ExternalSecret CRD for haven-api-secrets (#117 → relocated by #118, manual cutover bekliyor)

**KURAL**: Müşteriye "Haven compliant" denmeden önce tablodaki ⚠️/❌ maddelerinin **gerçek implementation'ı** doğrulanmalıdır. Sadece "kodda var" yetmez — `kubectl get nodes -L topology.kubernetes.io/zone`, `kubectl --token=$T get pods -n tenant-X`, ve `kubectl get pod ... -o jsonpath='{.spec.containers[*].image}'` gibi komutlarla canlı doğrulanır.

## Tamamlanan Phase'ler

### Phase -1: Dev Environment Setup ✅
- [x] Monorepo klasör yapısı
- [x] CLAUDE.md
- [x] .gitignore
- [x] api/pyproject.toml
- [x] infrastructure/ OpenTofu config
- [x] git init + ilk commit

### Phase 0: Haven K8s Cluster ✅
- [x] Hetzner base infra (hetzner-infra module)
- [x] Rancher management node (K3s + Helm, production-grade)
- [x] rancher2 provider (two-provider pattern: bootstrap + admin)
- [x] RKE2 cluster (rancher2_cluster_v2)
- [x] Cilium CNI (cni=cilium + chart_values, built-in Helm controller)
- [x] Longhorn storage (rancher2_app_v2, enable/disable)
- [x] Master/Worker nodes (cloud-init registration)
- [x] cloud-init bashism fix (dash uyumu)
- [x] Helm templates module'e taşındı (rancher-cluster module)
- [x] Cluster readiness: `rancher2_cluster_sync` (native, replaces bash curl loops)
- [x] App timeouts: all `rancher2_app_v2` have explicit timeouts (Longhorn 20m)
- [x] Destroy ordering: serialized (Longhorn last, 20m timeout)
- [x] Firewall: NodePort removed (Gateway API), hardening deferred (Hetzner public IP issue)

### Phase 0.5: Platform Servisleri ✅
- [x] Cert-Manager v1.16.2 (Jetstack repo via rancher2_catalog_v2, Haven #12)
- [x] rancher-monitoring 104.1.2 (Prometheus + Grafana, CRD + chart, Haven #14)
- [x] rancher-logging 104.1.2 (Banzai + Fluentbit/Fluentd, CRD + chart, Haven #13)
- [x] Harbor (image registry, rancher2_app_v2, harbor-system)
- [x] MinIO (S3 storage, rancher2_app_v2, minio-system, worker nodeSelector fix)

**11.5/15 Haven Compliant** (Phase 0.5 sonu durum — 1, 4, 15 partial/broken). **Sonraki: Phase 1 - Platform API + ArgoCD** (sprint scope kaydı tarihsel olarak korundu — gerçek 15/15 Sprint H1 sonunda geliyor).

### Phase 0.6: Cilium Gateway API + External Access ✅
- [x] Gateway API experimental CRDs (v1.2.1, tlsroutes dahil)
- [x] Cilium `gatewayAPI.enabled: true` (cilium-values.yaml.tpl)
- [x] GatewayClass `cilium` (Cilium operator oluşturdu)
- [x] Gateway `haven-gateway` (haven-gateway namespace, PROGRAMMED: True)
- [x] HTTPRoute: Harbor, MinIO Console, MinIO S3 (sslip.io hostnames)
- [x] Hetzner LB `use_private_ip: true` (firewall bypass, private network)
- [x] Hetzner LB targets: master + worker (6 node)
- [x] gateway-proxy DaemonSet (nginx, hostNetwork, port 80 → Cilium gateway ClusterIP)
- [x] Hetzner LB destination_port: 80 (firewall açık)
- [x] Dış erişim: Harbor HTTP 200, MinIO Console HTTP 200, MinIO S3 HTTP 403 ✅

### Phase 1 Sprint 1: Platform Servisleri (CNPG, ArgoCD, Keycloak) ✅
- [x] CloudNativePG operator 0.22.1 (cnpg-system, rancher2_app_v2)
- [x] CNPG Cluster `haven-platform` (haven_platform DB, cnpg-system, 1 instance, Longhorn 20Gi)
- [x] ArgoCD 7.7.3 (argocd namespace, insecure mode, HA disabled, HTTP 200)
- [x] Keycloak 26.1 (quay.io/keycloak/keycloak:26.1, start-dev, keycloak namespace, HTTP 302 → login)
- [x] External-DNS (optional, disabled, cloudflare provider ready)
- [x] Platform namespaces: haven-system, haven-builds
- [x] Gateway HTTPRoutes: argocd, keycloak, haven-api (placeholder)
- [x] Certificate SANs updated: argocd, keycloak, api sslip.io hostnames
- [x] Keycloak: ssh_resource ile kubectl apply (quay.io image, Bitnami chart abandon edildi)
- [x] Service selector fix: `kubectl delete svc` before apply (old Bitnami selector override)

### Phase 1 Sprint 2: Build/Deploy Pipeline + UI ✅
- [x] GitHub OAuth per-tenant (token stored server-side in DB)
- [x] Organization repo listing (read:org scope, NimbusProTch)
- [x] OAuth scope encoding fix (colon preservation in `read:user`)
- [x] Suspense boundary fix for OAuth callback page (Next.js 14)
- [x] **BuildKit** build engine (replaced Kaniko, 5x faster builds)
- [x] Nixpacks smart detection (Python/Node/Go/Ruby/Rust auto-detect start command)
- [x] Fallback Dockerfile generation when nixpacks fails
- [x] ARM64 (Apple Silicon) support for nixpacks binary
- [x] Private repo clone via embedded OAuth token in git URL
- [x] Init container log capture on build failures (git-clone, nixpacks, buildctl)
- [x] App CRUD: create, read, update (PATCH), delete with K8s cleanup
- [x] Tenant CRUD: create, delete with K8s namespace lifecycle
- [x] Configurable app port (not hardcoded 8000)
- [x] Pod readiness check before marking deployment as "running"
- [x] CrashLoopBackOff/ImagePullBackOff early detection → FAILED status
- [x] Graceful HTTPRoute skip when Gateway API CRD not installed
- [x] DB enum fix (DeploymentStatus values_callable)
- [x] CI/CD pipeline step visualization in UI (Clone→Detect→Build→Push→Deploy)
- [x] Auto-streaming build logs during active builds
- [x] Deployment status polling (5s interval while building)
- [x] App Settings tab with GitHub repo/branch dropdowns
- [x] "Use existing Dockerfile" toggle option
- [x] Tenant delete with slug confirmation dialog

### Phase 1 Sprint 3: Managed Services + Multi-Tenant E2E ✅
- [x] Everest entegrasyonu (PostgreSQL v17.7, MySQL v8.4.7, MongoDB v8.0.17)
- [x] Redis OpsTree Operator (standalone, dev ephemeral / prod persistent)
- [x] RabbitMQ Cluster Operator (dev 1 replica / prod 3 replicas)
- [x] MySQL/MongoDB credential provisioning (Everest admin secret → tenant namespace)
- [x] SSE lifecycle events (tenant provision/deprovision, service provision/deprovision)
- [x] Helm chart guard: skip Deployment/Service/HPA/HTTPRoute when image.repository empty
- [x] Multi-tenant E2E: 3 tenants (Rotterdam PG+Redis, Amsterdam MongoDB+Redis, Utrecht MySQL+RabbitMQ)
- [x] ArgoCD per-tenant ApplicationSet (appset-{slug}, multi-source: chart + gitops values)
- [x] Gitea haven-gitops repo with tenant/app values.yaml manifests
- [x] Harbor per-tenant projects + robot accounts
- [x] Build + Deploy pipeline E2E: build trigger → BuildKit → Harbor → Gitea values update → ArgoCD sync → Pod Running
- [x] 752 backend tests (all passing)

### Phase 1 Sprint 3.5: Post-E2E Hardening & Security ✅
- [x] Hardcoded credential temizliği (.env.example, config default'lar boş) — PR #6
- [x] DB unique constraints + race condition fix (IntegrityError → 409) — PR #7
- [x] Background loop per-service isolation (bir hata diğerlerini engellemez) — PR #8
- [x] Error handling cleanup (bare except fix, EmailStr validation) — PR #9
- [x] PG custom user via primary endpoint (PgBouncer bypass) — PR #10
- [x] URL-encode database passwords in DATABASE_URL — PR #5
- [x] CiliumNetworkPolicy everest egress + ResourceQuota artırma — PR #4
- [x] Everest namespace revert (everest ns, tenant ns'de secret) — PR #4
- [x] MySQL/MongoDB custom user provisioning (aiomysql, motor) — PR #4
- [x] Background credential provisioning loop (UI bağımlılığı kaldırıldı) — PR #4
- [x] 778 backend tests (all passing)

### Phase 1 Sprint 4.5: UX Overhaul + Pipeline Fix + Auth Hardening ✅
- [x] Fix: Create App slug validation (silent HTML5 pattern → JS validation with errors)
- [x] Fix: Pod readiness — detect terminated containers + init container failures
- [x] Fix: Queue page "unavailable" → show actual error + retry button
- [x] Fix: ObservabilityTab "Loading pods" → "No deployment yet" or retry
- [x] Add gitops_commit_sha field to Deployment model
- [x] Keycloak token: 5min → 1hr access, 8hr SSO session (haven-realm.json + setup script)
- [x] Frontend 401 interceptor with Promise-based mutex (race-condition safe)
- [x] Session expiry toast notification before redirect
- [x] Token refresh safety margin: 60s → 5min
- [x] New App wizard: 4-step form (Identity → Source → Build → Runtime → Review)
- [x] GitHubFileBrowser component (repo file tree dropdown for Dockerfile selection)
- [x] GitHubRepoPicker component (searchable, org-grouped repo picker)
- [x] Build vs Deploy separation: BUILT status, deploy-image endpoint
- [x] Pipeline: deploy=False stops after build (BUILT status)
- [x] SSE heartbeat fix (data: format for UI parser)
- [x] Auto-start log streaming on build/deploy
- [x] BUILT status UI support (badge, pipeline viz, deploy button)
- [x] AddServiceModal enterprise redesign with official DB logos + backup config
- [x] BackupPanel component (list backups, trigger snapshot, restore)
- [x] Backup API client methods (list, trigger, restore, schedule)
- [x] Build queue service (Redis FIFO, per-tenant concurrency limits)
- [x] Build queue endpoints (status, jobs, position) with graceful Redis fallback
- [x] Dashboard stats: gradient cards, app health dots
- [x] App cards: port, domain, mini deployment status, quick actions
- [x] Config validation: warn about missing recommended settings at startup
- [x] buildOnly() and deployImage() API client methods
- [x] 1081 backend tests (was 929, +152 new)

### Phase 1 Sprint 5: Broken Fields + Service Dependencies ✅
- [x] Backend: 9 broken field fix (deploy_service, auto_deploy, use_dockerfile, dockerfile_path, build_context, custom_domain, health_check_path, canary_enabled, canary_weight) — PR #47
- [x] Backend: requested_services + auto-connect on app create — PR #47
- [x] Backend: ArgoCD sync options (diff, prune, force, dry_run) — PR #47
- [x] Backend: connected_apps enrichment on service responses — PR #47
- [x] Backend: app services endpoint (GET /apps/{slug}/services) — PR #47
- [x] 1185 backend tests (was 1081, +104 new)

### Phase 1 Sprint 5.5: Frontend — Modals, Services UX, E2E ✅
- [x] Frontend: API client types + methods (AppServiceEntry, SyncDiffEntry, SyncOptions) — PR #48
- [x] Frontend: Wizard Step 5 "Services" (5 DB types, select/deselect, review) — PR #48
- [x] Frontend: ConnectedServicesPanel (status badges, credentials viewer, disconnect) — PR #48
- [x] Frontend: ScaleModal (replica presets, resource tiers, HPA, impact preview) — PR #48
- [x] Frontend: SyncModal (ArgoCD status, diff, options, history, dry run) — PR #48
- [x] Frontend: RestartModal (pod count, rolling restart warning, downtime info) — PR #48
- [x] Entegrasyon: Modal'ları app detail'e bağla — PR #49
- [x] Entegrasyon: ConnectedServicesPanel app detail'e ekle — PR #49
- [x] Entegrasyon: Provisioning banner — PR #49
- [x] Entegrasyon: Tenant services connected_apps — PR #49
- [x] 33 Playwright E2E tests + auth bypass fix — PR #50
- [x] 152 Playwright tests (was 36, +116 new)

### Phase 1 Sprint 4: Monorepo + Smart Detection (SONRAKI)
- [ ] Repo içindeki app'leri/dizinleri listeleme (GitHub API tree endpoint)
- [ ] Akıllı backend detection: framework + dependency analizi
- [ ] Auto-detect: DB ihtiyacı (SQLAlchemy, Prisma, TypeORM → PostgreSQL provision)
- [ ] Auto-detect: Redis ihtiyacı (redis-py, ioredis → Redis provision)
- [ ] Auto-detect: Queue ihtiyacı (pika, amqplib → RabbitMQ provision)
- [ ] UI'da dependency gösterimi: "Bu app PostgreSQL ve Redis kullanıyor"

### Phase 1 Sprint 5: Observability
- [ ] Grafana Loki (app log aggregation, per-tenant)
- [ ] Grafana Mimir (metrics, per-tenant)
- [ ] Grafana Tempo + OpenTelemetry Collector (distributed tracing)
- [ ] Per-app dashboard: logs, CPU/RAM, request rate, latency, traces
- [ ] UI'da log viewer, metric grafikler, trace explorer

### Phase 1 Sprint 6: Production Hardening
- [ ] Custom domain + TLS (cert-manager + Let's Encrypt)
- [ ] Webhook auto-deploy (git push → otomatik build+deploy)
- [ ] One-click rollback
- [ ] Health check konfigürasyonu (HTTP path, TCP, interval)
- [ ] Resource limits konfigürasyonu (CPU/RAM per app)
- [ ] Auto-scaling rules (HPA custom metrics)

## Teknik Gotchas

### iyziops Option B (kube-hetzner 2-LB + Hetzner CCM) — bootstrap traps

- **Hetzner CCM bootstrap deadlock**: A `helm.cattle.io/v1 HelmChart` resource for `hcloud-cloud-controller-manager` will NEVER complete on a fresh cluster with `--cloud-provider=external` because the helm-install Job pod uses RKE2's standard system addon pod template, which does NOT tolerate `node.cloudprovider.kubernetes.io/uninitialized:NoSchedule`. Every node has that taint until CCM runs, but CCM can't run until something tolerates the taint. **Fix**: install CCM as raw YAML (Deployment + ServiceAccount + ClusterRoleBinding) directly in `/var/lib/rancher/rke2/server/manifests/`. RKE2 applies raw manifests via the manifest applier (running inside rke2-server, not as a Pod), so no Job scheduling is involved. The CCM Deployment itself tolerates the uninitialized taint and runs `hostNetwork: true`. Source: `infrastructure/modules/rke2-cluster/manifests/hetzner-ccm.yaml.tpl`.

- **Cilium operator CRD detection at startup only**: Cilium operator checks Gateway API CRD presence ONCE at startup. If the CRDs are installed AFTER cilium-operator has started, the operator logs `"Required GatewayAPI resources are not found"` and never re-checks. **Fix**: `kubectl rollout restart deploy/cilium-operator -n kube-system` after the gateway-api-crds Application syncs. This is unavoidable on a fresh cluster because Cilium boots before ArgoCD (which installs the CRDs from upstream kubernetes-sigs/gateway-api). Documented in the Option B verification flow.

- **gateway-api-crds Application must NOT live in `platform/argocd/apps/ingress/`**: If you put the gateway-api-crds Application alongside Gateway/HTTPRoute/ReferenceGrant manifests in the same directory, ArgoCD's platform-ingress App tries to sync everything in a single transaction. The Gateway resources fail (CRDs missing) and ArgoCD never creates the Application. **Fix**: place the gateway-api-crds Application as a sibling under `platform/argocd/appsets/gateway-api-crds.yaml` (sync-wave: -10) so iyziops-root applies it before platform-ingress (sync-wave: -5).

- **cert-manager + Cloudflare wildcard cert cleanup race**: After a fresh cluster bootstrap, the iyziops-wildcard certificate may get stuck in `Issuing` because cert-manager's Cloudflare DNS-01 cleanup fails with `for DELETE "/zones//dns_records/<id>"` (empty zone ID in URL). Stale `_acme-challenge.iyziops.com` TXT records pile up and block fresh order processing. **Fix**: manually delete leftover TXT records via `curl -X DELETE "https://api.cloudflare.com/client/v4/zones/$ZONE/dns_records/$ID"`, then `kubectl delete certificate -n cert-manager iyziops-wildcard` and `kubectl rollout restart deploy/cert-manager -n cert-manager`. The Cloudflare token used must have **Zone:Read + DNS:Edit** on the iyziops zone (User:Read NOT required despite the cert-manager warning logs).

- **iyziops-platform-repo secret**: bootstrap manifest creates a repo Secret with `sshPrivateKey` field for the GitOps repo, but the repo is public over HTTPS. The vestigial `sshPrivateKey` field makes ArgoCD attempt SSH auth and fail with `ssh: no key found`. **Fix**: `kubectl patch secret -n argocd iyziops-platform-repo --type=json -p='[{"op":"remove","path":"/data/sshPrivateKey"}]'`. Long-term fix: drop sshPrivateKey from `infrastructure/modules/rke2-cluster/manifests/argocd-repo-secret.yaml.tpl` since the repo is public.

- **kube-hetzner / hcloud-k8s 2-LB pattern**: Hetzner CCM cannot share a single LB with tofu-managed services because `ReconcileHCLBServices` deletes any port not in the Service spec. The pattern is two distinct LBs: API LB (tofu-managed, 6443) + ingress LB (tofu shell with `lifecycle ignore_changes = [target, labels["hcloud-ccm/service-uid"]]`, CCM adopts via the `load-balancer.hetzner.cloud/name` annotation on the auto-generated cilium-gateway-* Service). The annotation must match the literal Hetzner LB name exactly.

### Original (Haven dev / older sprints)

- Hetzner primary IP limit ~5 per account → request increase for 3+3 nodes
- `HavenAdmin2026!` → `!` breaks in bash, never pass through shell
- rancher2 provider v5.x → Rancher 2.9.x (version must match)
- cloud-init `$$` for shell variable escaping in templatefile
- cloud-init `${VAR:0:16}` bash substring = Bad substitution (dash shell)
- Provider: `token_key` (provider config) vs `.token` (resource output)
- `cni: "none"` = chicken-and-egg problem → use `cni: "cilium"` + `chart_values`
- CIS profile taint: `node-role.kubernetes.io/etcd:NoExecute` → `tolerations: [{operator: "Exists"}]`
- `rancher2_app_v2` "Cluster not active" → `rancher2_cluster_sync` with `wait_catalogs=true` + `state_confirm=3`
- **Hetzner firewall**: Nodes use PUBLIC IPs for inter-node traffic, not private network → restricting to `network_cidr` breaks cluster. Need RKE2 `--node-ip` private network config first
- NodePort range (30000-32767) removed from firewall → Gateway API replaces it
- **Cilium 1.16 Gateway API + NodePort bug**: L7LB Proxy Port only applied to ClusterIP BPF entry, NOT NodePort entries → NodePort unreachable externally. Workaround: nginx DaemonSet (hostNetwork, port 80) proxies to gateway ClusterIP
- **nginx proxy_http_version**: Default is HTTP/1.0. Cilium Envoy gateway requires HTTP/1.1. Add `proxy_http_version 1.1; proxy_set_header Connection ""` to nginx config
- **Hetzner LB private IP**: `use_private_ip = true` + `depends_on = [hcloud_server_network.*]` bypasses public firewall for LB→node traffic
- **GatewayClass Unknown status**: Cilium 1.16 writes `supportedFeatures` as strings, but Gateway API CRD v1.2.1 expects objects → cosmetic only, Gateway itself works (PROGRAMMED: True)
- Longhorn destroy timeout → `timeouts { delete = "20m" }` + serialized destroy (Longhorn last)
- Longhorn destroy fallback: if 20m timeout, `tofu state rm 'rancher2_app_v2.longhorn[0]'` then re-destroy
- `nonsensitive()` in local-exec environment block to avoid output suppression
- cert-manager NOT in rancher-charts → use `rancher2_catalog_v2` (Jetstack repo) + `rancher2_app_v2`
- rancher-monitoring/logging need CRD chart installed first (e.g., `rancher-monitoring-crd`)
- Rancher 2.9.3 chart versions: `104.x.x` prefix (NOT `105.x.x`) → query live catalog API
- Longhorn version in catalog may differ from tfvars default → check `deployment_values` after apply
- **Bitnami images decommissioned**: `registry.bitnami.com` = NXDOMAIN, `docker.io/bitnami/*` tags removed, `ghcr.io/bitnami` = 403. Use official images (e.g. `quay.io/keycloak/keycloak:26.1`)
- **CNPG Cluster tolerations**: `spec.affinity.tolerations` NOT `spec.tolerations` (strict CRD validation)
- **Keycloak 26 start-dev**: management port 9000 not exposed → use `tcpSocket` probe on port 8080
- **kubectl apply + Service selector**: strategic merge patch does NOT remove extra labels from existing Service. Fix: `kubectl delete svc <name> --ignore-not-found` before `kubectl apply` to reset selector cleanly
- **ssh_resource via Rancher fleet secret**: `kubectl get secret -n fleet-default ${cluster_name}-kubeconfig -o jsonpath='{.data.value}' | base64 -d > /tmp/workload-kubeconfig` gives RKE2 cluster access from K3s management node
- **base64encode() trick for kubectl apply**: `echo '${base64encode(yaml)}' | base64 -d | kubectl apply -f -` avoids heredoc/escaping issues in ssh_resource commands

- **BuildKit > Kaniko**: Kaniko 15+dk, BuildKit 3-4dk (5x hız). BuildKit paralel layer build + akıllı cache. `moby/buildkit:rootless` + `--oci-worker-no-process-sandbox` Kind'da çalışır
- **BuildKit daemon**: `buildkitd` Deployment + Service (`tcp://buildkitd.haven-builds.svc:1234`), `buildctl` Job olarak build submit
- **Nixpacks ARM64**: `aarch64-unknown-linux-musl` binary indirmeli, `uname -m` ile detect
- **Nixpacks "No start command"**: Otomatik tespit: Python (main.py, app.py, FastAPI/Flask/Django), Node (package.json scripts.start), Go (main.go), fallback Dockerfile üretimi
- **Kind insecure registry**: containerd config.toml'a `[plugins."io.containerd.grpc.v1.cri".registry.mirrors]` + `[...registry.configs...tls]` ekle, `/etc/hosts`'a ClusterIP ekle, `systemctl restart containerd`
- **GitHub OAuth org repos**: `read:org` scope + `/user/orgs` → `/orgs/{login}/repos` endpoint'leri ile org repo'ları listele
- **GitHub private repo clone**: `https://oauth2:{token}@github.com/owner/repo.git` — token DB'de tenant bazında sakla, build sırasında clone URL'ye inject et
- **SQLAlchemy Enum case**: `Enum(MyEnum, values_callable=lambda e: [x.value for x in e])` — DB lowercase, Python uppercase uyumsuzluğu
- **Next.js 14 useSearchParams**: Suspense boundary zorunlu, `export const dynamic = "force-dynamic"` ile cache engelle
- **App port konfigürasyonu**: Dockerfile EXPOSE portu ile liveness probe portu eşleşmeli, `Application.port` field ile konfigüre et

## Maliyet

| Ortam | Aylık |
|-------|-------|
| Dev cluster (Hetzner) | ~€177 |
| Runner VPS (Hetzner CX22) | €4.49 |
| Anthropic Max | $200 |
| **Toplam (dev)** | **~€182 + $200** |

## ZORUNLU KURALLAR (ASLA İHLAL EDİLEMEZ)

### Kural 1: Test Yazılmadan Hiçbir Şey "OK" Değildir
- Her yeni feature/fix için YENİ test yazılmalı
- Test sayısı HER sprint sonunda ARTMALI — aynı kalırsa test yazılmamış demektir
- "492 test geçiyor" eski testlerin geçmesi demek, yeni kodun test edilmesi DEĞİL
- Önce test yaz (FAIL etmeli) → sonra kodu yaz → test geçmeli
- Integration kodu (ör: Everest client) entegre edilmeden task TAMAMLANMIŞ SAYILMAZ

### Kural 2: Sprint Adım Sırası (Kesinlikle Bu Sırada)
1. Backend kodu yaz + backend testi yaz + backend test ÇALIŞTIR
2. DB/K8s/Gitea/Harbor entegrasyonu doğrula (gerçek cluster'da)
3. UI kodu yaz + Playwright testi yaz + test ÇALIŞTIR
4. Tüm test suite çalıştır (eski + yeni)
5. Test count artmadıysa → ADIM 1'E DÖN
6. PR oluştur → review → merge

### Kural 3: PR ve Review
- Her değişiklik feature branch'te yapılır
- PR oluşturulmadan main'e merge yasak
- Her PR'da: hangi testler eklendi, test count öncesi/sonrası belirtilmeli

### Kural 4: Entegrasyon = Bağlama + Test
- Client/service yazmak YETERLİ DEĞİL
- Client'ı çağıran kodu da yazmak lazım (ör: managed_service.py → everest_client)
- Entegrasyon testi lazım (ör: Everest'ten gerçek DB oluştur, status kontrol et)
- "Client hazır" ≠ "Feature tamamlandı"

### Kural 5: CLAUDE.md ve Plan Güncel Tutulmalı
- Her sprint sonunda CLAUDE.md güncellenmeli (yeni mimari kararlar, tamamlanan fazlar)
- Plan dosyası güncel tutulmalı
- Yeni gotcha'lar eklenmeli

### Kural 6: DB Migration Kontrolü (Alembic)
- Her SQLAlchemy model değişikliğinde Alembic migration YAZILMALI
- `alembic upgrade head` init container'da otomatik çalışır — **ASLA `stamp head` kullanılmaz**
- Deploy sonrası migration doğrulanmalı:
  ```bash
  kubectl exec -n haven-system deploy/haven-api -- python -m alembic -c alembic/alembic.ini current
  ```
- Migration uygulanmamışsa → pod restart: `kubectl rollout restart deploy/haven-api -n haven-system`
- **Test**: Yeni kolon/tablo eklendiyse, API endpoint'i o kolonu döndürüyorsa → cluster'da curl ile doğrula

### Kural 7: CORS Testi (Her API Deploy Sonrası)
- Her API değişikliğinden sonra browser'dan test edilmeli (curl CORS hatası göstermez!)
- Console'da `Access-Control-Allow-Origin` hatası varsa → merge YASAK
- Exception handler'lar CORS headers içermeli (500/422/403 response'ları dahil)
- Test komutu:
  ```bash
  curl -s -H "Origin: https://app.46.225.42.2.sslip.io" \
    -I https://api.46.225.42.2.sslip.io/api/docs | grep -i "access-control"
  ```

## Mevcut Durum (2026-03-31)

### Cluster Erişimi
- **Kubeconfig**: `infrastructure/environments/dev/kubeconfig`
- **Cluster API**: `https://46.225.42.2:6443` (Hetzner, Rancher-managed RKE2)
- **Kullanım**: `export KUBECONFIG=/path/to/InfraForge-Haven/infrastructure/environments/dev/kubeconfig`
- **API lokal başlatma**:
  ```bash
  cd api
  K8S_KUBECONFIG=../infrastructure/environments/dev/kubeconfig \
  EVEREST_URL=http://localhost:8888 \
  HARBOR_URL=http://harbor.46.225.42.2.sslip.io \
  HARBOR_ADMIN_PASSWORD='HavenHarbor2026!' \
    .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```
- **Everest port-forward**: `kubectl port-forward -n everest-system svc/everest 8888:8080`
- **Keycloak port-forward**: `kubectl port-forward -n keycloak svc/keycloak-keycloakx-http 8080:80`
- **Keycloak lokal**: `http://localhost:8080` (haven realm, haven-ui client, admin / HavenAdmin2026!)
- **Gitea port-forward**: `kubectl port-forward -n gitea-system svc/gitea-http 3030:3000`
- **Gitea login**: `http://localhost:3030` (havenAdmin / HavenAdmin2026)
- **Harbor external**: `http://harbor.46.225.42.2.sslip.io` (admin/HavenHarbor2026!)

### Cluster Bileşenleri
- 6 node RKE2 cluster (3 master, 3 worker) — Hetzner dev
- **ArgoCD**: haven-platform, haven-api, haven-ui → Synced+Healthy
- **Gitea**: gitea-system ns, haven/haven-gitops repo (tenant manifests AKTİF — her app'in values.yaml'ı burada)
- **Harbor**: harbor-system ns, `haven` project, tenant image'ları `haven/tenant-{slug}/{app}:{tag}` altında
- **Keycloak**: keycloak ns, haven realm, haven-api + haven-ui client'lar
- **BuildKit**: haven-builds ns, `buildkitd` Deployment (dockerfile build + harbor push)
- **Redis Operator**: OpsTree, redis-system ns (tenant Redis instance'ları tenant ns'de oluşur)
- **RabbitMQ Operator**: rabbitmq-system ns (tenant RabbitMQ instance'ları tenant ns'de oluşur)
- **CNPG**: cnpg-system ns (platform DB: haven_platform)
- **Percona Everest v1.13.0**: everest-system ns, 3 DB engine (PG, MySQL, MongoDB) operational

### Namespace Yapısı (3-Tenant Deploy Sonrası)
```
everest                  → Everest-managed DB pod'ları
                           rotterdam-app-pg-instance1-*   (PostgreSQL 17.7 + PgBouncer)
                           amsterdam-app-mongo-rs0-0      (MongoDB 8.0.17)
                           utrecht-app-mysql-pxc-0        (MySQL 8.4.7 + HAProxy)
tenant-rotterdam         → rotterdam-api + app-redis-0
tenant-amsterdam         → amsterdam-portal + app-redis-0
tenant-utrecht           → utrecht-worker + app-rabbit-server-0
harbor-system            → Image registry (tenant-rotterdam/amsterdam/utrecht projects)
haven-builds             → BuildKit daemon + build job pod'ları
```

### App Deploy Akışı (E2E DOĞRULANDI — 3 Tenant)
```
1. POST /tenants                      → Tenant oluştur (ns, quota, RBAC, CNP, Harbor, AppSet)
2. POST /tenants/{slug}/apps          → App kaydı oluştur + Gitea values.yaml yaz
3. POST /tenants/{slug}/services      → Managed service provision (Everest/CRD)
4. POST /apps/{slug}/build            → Build trigger (background task)
5. BuildKit: git clone → Dockerfile build → Harbor push
6. Pipeline: Gitea values.yaml image tag güncelle → ArgoCD sync → Pod Running
7. GET /tenants/{slug}/events         → SSE ile adım adım progress stream
```
- **Deploy mode**: GitOps (ArgoCD ApplicationSet per tenant, multi-source Helm)
- **Gitea GitOps**: AKTİF — `tenants/{slug}/{app}/values.yaml` ArgoCD tarafından izleniyor
- **Harbor image format**: `harbor.46.225.42.2.sslip.io/library/tenant-{slug}/{app}:{commit[:8]}`
- **Scaling**: `PATCH /apps/{slug}` ile `replicas` güncellenebilir
- **SSE Events**: Tenant provision/deprovision + service provision adım adım stream

### Managed Services (Sprint B+C TAMAMLANDI)
- **5 DB tipi gerçek cluster'da E2E doğrulandı** (Playwright + curl):
  - PostgreSQL (Everest) — ~50s ready, credentials: user/pass/host/pgbouncer-host/port
  - MySQL (Everest) — ~3.5dk ready, 2Gi RAM + 5Gi storage override (OOMKilled fix)
  - MongoDB (Everest) — ~1.5dk ready
  - Redis (CRD, OpsTree) — ~22s ready, passwordless, fsGroup:1000 + podSecurityContext gerekli
  - RabbitMQ (CRD) — ~1.5dk ready, credentials: username/password/host/port/connection_string
- **Tenant prefix izolasyonu**: Everest DB adı `{tenant_slug}-{service_name}` (ör: `testing-app-pg`)
- **Health check**: Everest API (PG/MySQL/MongoDB), Pod readiness fallback (Redis), CRD conditions (RabbitMQ)
- **DEGRADED status**: OOMKilled, CrashLoopBackOff, ImagePullBackOff otomatik detect + error_message
- **Credentials endpoint**: `/services/{name}/credentials` → tüm K8s secret key'lerini base64 decode edip döner
- **Backup**: PITR disabled (default), backup_service.py CRD-based var, Everest backup API henüz entegre değil

### Full E2E Doğrulama (3 Tenant — 2026-03-31)
```
✅ Tenant create → namespace + quota + RBAC + CNP + Harbor + AppSet (3 tenant)
✅ App create → Gitea values.yaml + ArgoCD Application (3 app)
✅ Service provision → Everest PG/MySQL/MongoDB + CRD Redis/RabbitMQ (6 service, all READY)
✅ Build trigger → BuildKit → Harbor push (3 build, all Completed)
✅ Gitea values.yaml image update → ArgoCD sync → Pod Running (3 app Running)
✅ Credential provisioning → svc-* secret in tenant namespace (PG/MySQL/MongoDB/Redis/RabbitMQ)
✅ ArgoCD: 3 AppSets + 3 tenant apps + 3 platform apps = all Healthy
✅ Gitea: tenants/rotterdam/rotterdam-api, tenants/amsterdam/amsterdam-portal, tenants/utrecht/utrecht-worker
✅ Harbor: tenant-rotterdam, tenant-amsterdam, tenant-utrecht projects
✅ Delete tenant → cascade apps + services + namespace + AppSet + Harbor (verified)
```

### GitHub OAuth
- Backend: `api/app/routers/github.py` — OAuth flow var (authorize → callback → token DB'ye kayıt)
- Tenant'a `github_token` PATCH ile de set edilebilir
- Build pipeline: tenant'ın `github_token`'ını kullanarak private repo clone yapabiliyor

### Test Durumu
- Backend unit testleri: **1185** (Sprint 5: broken fields, service deps, ArgoCD sync, connected_apps — +104 yeni)
- Playwright E2E: **152 test** (Sprint 5.5: modals, services panel, wizard, provisioning banner, auth fix — +116 yeni)
- Real cluster E2E: 3 tenants × (app + 2 services + build + deploy + delete) — all verified
- CI/CD: GitHub Actions → Lint ✅ → Test (929) ✅ → Docker Build ✅ → Harbor Push ✅ → Manifest Update ✅ → ArgoCD Sync ✅

### CI/CD Pipeline
- **GitHub Actions**: `api-ci.yml` (lint → test → build → push → manifest update)
- **Image**: `harbor.46.225.42.2.sslip.io/library/haven-api:{git-sha}`
- **ArgoCD**: `haven-api` Application auto-syncs from `platform/manifests/haven-api/`
- **Swagger docs**: `https://api.46.225.42.2.sslip.io/api/docs`
- **ReDoc**: `https://api.46.225.42.2.sslip.io/api/redoc`

### Enterprise Hardening (Sprint H1-H3)
- **RBAC**: `require_role("owner", "admin")` decorator, POST /members enforced
- **Container security**: Non-root (USER 1000), drop ALL capabilities, startup probe
- **Request logging**: X-Request-ID correlation header, latency logging
- **Config validation**: Missing SECRET_KEY/DATABASE_URL warning at startup
- **Backup**: MinIO S3 HTTPS, Everest DatabaseClusterBackup, MongoDB/MySQL/PG verified

### Bilinen Sorunlar / Gotcha'lar
- **Redis connection_hint**: OpsTree operator service adı `{name}` (NOT `{name}-redis`) → fix edildi
- **PG password URL-encoding**: Everest random password'lerde özel karakterler var (`:?()=|{}@`), kullanıcı `urllib.parse.quote` ile encode etmeli
- **Everest PG default DB**: `postgres` (custom DB adı oluşturmuyor, connection_hint'teki DB adı yanlış olabilir)
- **Harbor URL**: Build pipeline'da `HARBOR_URL` env var set edilmeli, docker config secret'taki host ile match etmeli
- **apptype enum**: DB'de yoksa manual oluştur: `CREATE TYPE apptype AS ENUM ('web', 'worker', 'cron')`
- **MySQL memory**: PXC 8.4 + Galera minimum **3Gi** RAM for backup SST (2Gi OOMKill during xtrabackup), 5Gi storage
- **Redis fsGroup**: OpsTree Redis Operator CRD'deki `securityContext.fsGroup` alanını StatefulSet'e **aktarmıyor**. Çözüm: Dev tier'da persistent storage kaldırıldı (ephemeral Redis). Prod tier'da init container veya volume ownership fix gerekli.
- **Redis passwordless tenant secret**: OpsTree Redis secret oluşturmuyor. `_create_crd_tenant_secret` sadece `REDIS_URL` ile secret yaratır.
- **ArgoCD per-tenant AppSet**: Global ApplicationSet kaldırıldı. Her tenant için `appset-{slug}` K8s API ile oluşturuluyor (tenant_service.py). haven-platform sadece haven-api + haven-ui yönetiyor.
- **Everest CPU minimum**: Everest v1.13 `CPU limits should be above 600m` — 600m dahil değil! Dev tier `1` core olarak set edildi. Bu fix öncesi Everest 400 dönüyordu → CRD fallback → sync stuck.
- **EVEREST_URL**: configmap'e eklendi (`http://everest.everest-system.svc.cluster.local:8080`). Yoksa Everest path hiç çalışmaz.
- **Backup**: DB oluşturulurken backup config default disabled (`pitr.enabled: false`)
- **Redis passwordless**: OpsTree Redis şifresiz çalışıyor — prod'da güvenlik riski
- **Gitea tenant manifest**: scaffold_service/delete_service kaldırıldı — DB'ler GitOps ile değil direkt API ile yönetiliyor
- **DB migration**: ✅ ÇÖZÜLDÜ — Alembic 0019 migration eklendi (unique constraints). Lokal dev DB'de `create_all()` veya `alembic upgrade head` ile tüm tablolar oluşturulmalı.
- **GITOPS_GITHUB_TOKEN**: haven-api-secrets'ta `GITOPS_GITHUB_TOKEN` varsa ve GitHub token'ı ise Gitea'ya bağlanamaz. Bu key kaldırılmalı — `GITEA_ADMIN_TOKEN` yeterli.
- **Helm chart empty image guard**: `image.repository` boşken Deployment/Service/HPA/HTTPRoute oluşturulmamalı. `{{- if .Values.image.repository }}` guard eklendi. Aksi halde `:latest` image → InvalidImageName.
- **MySQL/MongoDB credential provisioning**: ✅ ÇÖZÜLDÜ (PR #4) — `aiomysql` ve `motor` ile custom user/db oluşturuluyor. Fallback: admin creds kopyalama.
- **ArgoCD auto-sync wipe protection**: Helm chart image guard sonrası tüm resources siliniyor → ArgoCD "auto-sync will wipe out all resources" uyarısı ile auto-sync engelliyor. Manuel sync gerekli.
- **haven-api image build (ARM64 → AMD64)**: Local Mac'te build edince `exec format error`. `docker build --platform linux/amd64` zorunlu.
- **Gitea admin password**: `must-change-password` flag'i set edilmiş olabilir. `gitea admin user change-password --must-change-password=false` ile reset gerekli. Güncel: havenAdmin / HavenAdmin2026
- **Port-forward'lar**: haven-api svc port 80 (not 8000!), keycloak svc `keycloak-keycloakx-http` port 80
- **CiliumNetworkPolicy everest egress**: ✅ ÇÖZÜLDÜ (PR #4) — Tenant CNP'ye everest namespace egress eklendi. Yeni tenant'larda otomatik.
- **App port**: rotterdam-api 8080 dinliyor, default 8000 değil. App oluşturulurken doğru port belirtilmeli.
- **GITOPS_ARGOCD_REPO_URL**: ArgoCD cluster içinde çalışır, lokal `localhost:3030` URL'sine erişemez. `GITOPS_ARGOCD_REPO_URL=http://gitea-http.gitea-system.svc.cluster.local:3000/haven/haven-gitops.git` set edilmeli.
- **PG custom user**: `create_custom_database()` primary endpoint üzerinden bağlanır (PgBouncer bypass). App credential'larında HA endpoint döner. Lokal dev'de cluster-internal DNS erişilemez → admin creds fallback kullanılır.
- **Background credential loop**: 15sn aralığı, per-service isolation. Her service kendi session+transaction'ında işlenir. Bir service fail ederse diğerleri etkilenmez.
- **Config credential default'lar boş**: `keycloak_admin_password`, `harbor_admin_password`, `everest_admin_password`, `secret_key` default `""`. `.env` dosyasında set edilmeli.
- **DB unique constraints**: `applications(tenant_id, slug)`, `managed_services(tenant_id, name)` compound unique. Concurrent create → IntegrityError → 409.
- **DB migration**: Alembic 0019 — unique constraint migration. Lokal DB'de `create_all()` ile tablolar oluşturulabilir ama prod'da `alembic upgrade head` gerekli.
- **PATCH image_tag guard**: PATCH /apps image_tag None ise GitOps values.yaml güncellenmez (boş image yazıp Deployment'ı silmeyi engeller). İlk build sonrası image_tag set olur.
- **ArgoCD deploy fallback**: ArgoCD API erişilemezse pipeline K8s Deployment'ı direkt kontrol eder (60sn timeout). Pod Running ise status=RUNNING olur.
- **Vault prod**: Vault dev mode cluster'da çalışıyor. Prod için HA mode + persistent storage + auto-unseal gerekli.
- **haven-api image stale**: `platform/manifests/haven-api/deployment.yaml` image tag manual güncellenmeli. Her PR sonrası `docker build + push + image tag update` gerekli.
