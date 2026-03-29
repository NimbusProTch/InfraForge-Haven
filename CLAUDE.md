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

## Haven Compliancy (15/15 Zorunlu)

| # | Check | Çözüm | Status |
|---|-------|-------|--------|
| 1 | Multi-AZ | Falkenstein + Nuremberg (kodda var) | ✅ |
| 2 | 3+ master, 3+ worker | Kodda var (dev'de 1+1, IP limiti) | ✅ |
| 3 | CNCF Conformance | RKE2 certified | ✅ |
| 4 | kubectl erişim | Self-managed | ✅ |
| 5 | RBAC | RKE2 default | ✅ |
| 6 | CIS Hardening | RKE2 CIS profile (tolerations eklendi) | ✅ |
| 7 | CRI | RKE2 containerd | ✅ |
| 8 | CNI | Cilium (cni=cilium + chart_values) | ✅ |
| 9 | Separate master/worker | Ayrı VM'ler | ✅ |
| 10 | RWX Storage | Longhorn (rancher2_app_v2) | ✅ |
| 11 | Auto-scaling | HPA (built-in) + metrics-server (RKE2) | ✅ |
| 12 | Auto HTTPS | Cert-Manager (Jetstack repo, rancher2_catalog_v2) | ✅ |
| 13 | Log aggregation | rancher-logging (Banzai + Fluentbit/Fluentd) | ✅ |
| 14 | Metrics | rancher-monitoring (Prometheus + Grafana) | ✅ |
| 15 | Image SHA | RKE2 default | ✅ |

**KURAL: 15/15 geçmeden Phase 1'e geçilmez.**

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

**15/15 Haven Compliant! Sonraki: Phase 1 - Platform API + ArgoCD**

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

### Phase 1 Sprint 3: Monorepo + Akıllı Detection (SONRAKI)
- [ ] `dockerfile_path` — Hangi Dockerfile kullanılacak (`backend/Dockerfile`)
- [ ] `build_context` — Build root dizini (`./backend`)
- [ ] Repo içindeki app'leri/dizinleri listeleme (GitHub API tree endpoint)
- [ ] Akıllı backend detection: framework + dependency analizi
- [ ] Auto-detect: DB ihtiyacı (SQLAlchemy, Prisma, TypeORM → PostgreSQL provision)
- [ ] Auto-detect: Redis ihtiyacı (redis-py, ioredis → Redis provision)
- [ ] Auto-detect: Queue ihtiyacı (pika, amqplib → RabbitMQ provision)
- [ ] UI'da dependency gösterimi: "Bu app PostgreSQL ve Redis kullanıyor"

### Phase 1 Sprint 4: Managed Services
- [ ] OpenEverest entegrasyonu (MySQL, PostgreSQL, MongoDB — prod-ready)
- [ ] Redis Official Operator (Sentinel/Cluster mode)
- [ ] RabbitMQ Official Operator (queue management)
- [ ] Env var management UI (key-value editor, K8s Secrets)
- [ ] Internal service discovery (same-cluster endpoints, auto env injection)
- [ ] Connection string template: `postgresql://user:pass@cnpg-cluster.ns.svc:5432/db`

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

## Mevcut Durum (2026-03-29)

### Cluster
- 6 node RKE2 cluster (3 master, 3 worker) — Hetzner dev
- ArgoCD: main branch izliyor, Synced+Healthy
- Gitea: haven/haven-gitops repo, tenants/ dizini hazır
- Harbor: çalışıyor, CI image push başarılı
- Keycloak: haven realm, haven-api + haven-ui client'lar
- Redis: git queue için çalışıyor
- CNPG: platform DB çalışıyor
- Percona Everest v1.13.0: 3 DB engine (PG, MySQL, MongoDB) operational
- BuildKit: çalışıyor (haven-builds namespace)

### GitOps Akışı
```
GitHub (InfraForge-Haven) → Platform kodu + Helm charts + ApplicationSets
Gitea (haven-gitops)      → Tenant values.yaml (API oluşturur, git-worker push eder)

ApplicationSets (GLOBAL, GitHub'da):
  tenant-apps.yaml    → tenants/*/apps/*/values.yaml tarar (Gitea)
  tenant-services.yaml → tenants/*/services/*/values.yaml tarar (Gitea)

App-of-apps (ArgoCD):
  haven-platform → apps/ (haven-api, haven-ui) + applicationsets/ (tenant discovery)
```

### Everest Entegrasyonu
- Everest URL: http://everest.everest-system.svc.cluster.local:8080
- Admin: admin / HavenEverest2026
- PostgreSQL, MySQL, MongoDB → Everest API ile oluşturulacak
- Redis, RabbitMQ → Direct K8s CRD (OpsTree, RabbitMQ Operator)
- `api/app/services/everest_client.py` yazıldı AMA `managed_service.py`'ye entegre EDİLMEDİ

### Test Durumu
- Backend unit testleri: 492 (yeni feature testleri EKSİK)
- Playwright E2E: 48 test (UI smoke + API CRUD + auth + navigation)
- Everest entegrasyon testi: YOK
- Git worker E2E testi: YOK (git binary fix deploy bekleniyor)
- Build pipeline E2E testi: YOK
- DB provisioning E2E testi: YOK

### Bilinen Sorunlar
- Git worker: yeni image (906e6c8) deploy edildi ama ArgoCD manifest'i henüz sync olmadı
- GitHub OAuth: auth endpoint'ler public yapıldı ama UI'da test edilmedi
- Everest client yazıldı ama managed_service.py'ye entegre değil
- UI tema: CSS variables güncellendi ama hardcoded hex renkler var (refactor lazım)
