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
- [ ] Harbor (image registry, Phase 1'de)

**15/15 Haven Compliant! Sonraki: Phase 1 - Platform API + ArgoCD**

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
- Longhorn destroy timeout → `timeouts { delete = "20m" }` + serialized destroy (Longhorn last)
- Longhorn destroy fallback: if 20m timeout, `tofu state rm 'rancher2_app_v2.longhorn[0]'` then re-destroy
- `nonsensitive()` in local-exec environment block to avoid output suppression
- cert-manager NOT in rancher-charts → use `rancher2_catalog_v2` (Jetstack repo) + `rancher2_app_v2`
- rancher-monitoring/logging need CRD chart installed first (e.g., `rancher-monitoring-crd`)
- Rancher 2.9.3 chart versions: `104.x.x` prefix (NOT `105.x.x`) → query live catalog API
- Longhorn version in catalog may differ from tfvars default → check `deployment_values` after apply

## Maliyet

| Ortam | Aylık |
|-------|-------|
| Dev cluster (Hetzner) | ~€177 |
| Runner VPS (Hetzner CX22) | €4.49 |
| Anthropic Max | $200 |
| **Toplam (dev)** | **~€182 + $200** |
