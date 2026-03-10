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
│   │   ├── rancher-cluster/     # Rancher üzerinden cluster
│   │   ├── hetzner-infra/       # VM, Network, LB, Firewall
│   │   ├── openstack-infra/     # Cyso/Leafcloud (Phase 2+)
│   │   └── dns/                 # Cloudflare DNS
│   ├── environments/
│   │   ├── dev/                 # Hetzner dev cluster
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
- State: remote backend (S3-compatible, Phase 0+)

### Git
- Branch: `feature/{phase}-{description}` veya `fix/{description}`
- Commit: conventional commits (feat:, fix:, infra:, docs:)
- Her task = 1 commit
- PR gerekli değil (küçük ekip), direkt main'e push

### Genel
- Dil: Türkçe (kod yorumları, commit mesajları, dokümantasyon)
- Kod içi değişken/fonksiyon isimleri: İngilizce
- Secret'lar: .env dosyası (git'e eklenmez), prod'da K8s Secret/Vault

## Haven Compliancy (15/15 Zorunlu)

| # | Check | Çözüm | Status |
|---|-------|-------|--------|
| 1 | Multi-AZ | Falkenstein + Nuremberg | ⬜ |
| 2 | 3+ master, 3+ worker | RKE2 6 node | ⬜ |
| 3 | CNCF Conformance | RKE2 certified | ⬜ |
| 4 | kubectl erişim | Self-managed | ⬜ |
| 5 | RBAC | RKE2 default | ⬜ |
| 6 | CIS Hardening | RKE2 CIS profile + AppArmor | ⬜ |
| 7 | CRI | RKE2 containerd | ⬜ |
| 8 | CNI | Cilium | ⬜ |
| 9 | Separate master/worker | Ayrı VM'ler | ⬜ |
| 10 | RWX Storage | Longhorn | ⬜ |
| 11 | Auto-scaling | HPA + VPA | ⬜ |
| 12 | Auto HTTPS | Cert-Manager | ⬜ |
| 13 | Log aggregation | Grafana + Loki | ⬜ |
| 14 | Metrics | Metrics Server + Mimir | ⬜ |
| 15 | Image SHA | RKE2 default | ⬜ |

**KURAL: 15/15 geçmeden Phase 1'e geçilmez.**

## Mevcut Phase

**Phase -1: Dev Environment Setup** (aktif)
- [x] Monorepo klasör yapısı
- [x] CLAUDE.md
- [x] .gitignore
- [x] api/pyproject.toml
- [x] infrastructure/ OpenTofu config
- [x] git init + ilk commit

**Sonraki: Phase 0 - Haven Compliant Cluster**

## Maliyet

| Ortam | Aylık |
|-------|-------|
| Dev cluster (Hetzner) | ~€177 |
| Runner VPS (Hetzner CX22) | €4.49 |
| Anthropic Max | $200 |
| **Toplam (dev)** | **~€182 + $200** |
