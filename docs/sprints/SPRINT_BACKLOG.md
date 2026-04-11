# Haven Platform — Sprint Backlog

> Son güncelleme: 2026-04-10
> Durum: Sprint 1 başlamadı

---

## Sprint 1: 15/15 Haven Compliance + Güvenlik Fix'leri
**Branch**: `feature/sprint1-haven-compliance`
**Durum**: ⏳ Başlamadı
**Tahmini**: 1-2 gün

### Task'lar

- [ ] **1.1 OIDC Client ID Fix** (CRITICAL)
  - Dosya: `infrastructure/environments/dev/main.tf`
  - Satır 252 ve 357: `oidc-client-id=kubernetes` → `oidc-client-id=${var.keycloak_oidc_client_id}`
  - Doğrulama: tofu plan çıktısında `haven-kubectl` görünmeli

- [ ] **1.2 Multi-AZ Master Quorum Fix** (CRITICAL)
  - Dosya: `infrastructure/environments/dev/variables.tf` — master_count default 3 → 4
  - Dosya: `infrastructure/environments/dev/main.tf` — distribution formula: 2+2 (primary+secondary)
  - Doğrulama: tofu plan'da 4 master, 2x nbg1 + 2x fsn1

- [ ] **1.3 Longhorn Cross-AZ Replikasyon**
  - Dosya: `infrastructure/environments/dev/helm-values/longhorn.yaml`
  - replicaAutoBalance + topologySpreadConstraints ekle
  - Doğrulama: StorageClass spec'inde zone-aware config

- [ ] **1.4 Remote State Backend (Hetzner S3)**
  - Dosya: `infrastructure/environments/dev/backend.tf` — S3 backend uncomment + configure
  - Doğrulama: backend config valid, `tofu init` çalışır

- [ ] **1.5 Operator CIDR Kısıtlama**
  - Dosya: `infrastructure/environments/dev/variables.tf` — default "0.0.0.0/0" → boş (zorunlu input)
  - Validation block ekle: boş olamaz
  - Doğrulama: variable validation hata veriyor

- [ ] **1.6 BuildKit Security Context**
  - Dosya: `api/app/services/build_service.py` (~satır 402)
  - Pod spec'e: runAsNonRoot, runAsUser=1000, drop ALL capabilities
  - Doğrulama: pytest testleri geçiyor

- [ ] **1.7 WireGuard + Audit Logging tfvars**
  - Dosya: `infrastructure/environments/dev/variables.tf` — enable_wireguard default true doğrula
  - Doğrulama: template render'da encryption block var

### Test Planı
- `cd api && python -m pytest tests/ -q` — tüm testler geçmeli
- `cd api && ruff check . && ruff format --check .` — lint clean
- `tofu validate` — HCL syntax valid (apply yok)
- Architect agent: kod review + güvenlik
- Tester agent: test suite çalıştır

### Definition of Done
- [ ] Tüm task'lar tamamlandı
- [ ] Architect agent approved
- [ ] Tester agent approved (tüm testler geçti)
- [ ] PR oluşturuldu, merge-ready
- [ ] CLAUDE.md güncellendi

---

## Sprint 2: Kyverno Policy Engine
**Branch**: `feature/sprint2-kyverno`
**Durum**: ⏳ Sprint 1 bitmesini bekliyor
**Tahmini**: 1 gün
**Bağımlılık**: Sprint 1 merged

### Task'lar

- [ ] **2.1 Kyverno ArgoCD Application**
  - Yeni dosya: `platform/argocd/apps/kyverno.yaml`
  - Chart: kyverno/kyverno v3.x, 3 replica, PDB, HPA
  - Namespace: kyverno-system

- [ ] **2.2 System Namespace Exclusion**
  - ~20 namespace excluded (kyverno, kube-system, argocd, haven-system, longhorn-system, ...)

- [ ] **2.3 Policy: restrict-registries** (Validate)
  - Yeni dosya: `platform/kyverno-policies/restrict-registries.yaml`
  - Sadece Harbor registry, tenant-* namespace'lere uygulanır

- [ ] **2.4 Policy: disallow-privileged** (Validate)
  - Yeni dosya: `platform/kyverno-policies/disallow-privileged.yaml`
  - privileged: false, runAsNonRoot, drop ALL, no hostPath

- [ ] **2.5 Policy: require-resource-limits** (Validate)
  - Yeni dosya: `platform/kyverno-policies/require-resource-limits.yaml`
  - CPU/memory limits + requests zorunlu

- [ ] **2.6 Policy: require-tenant-labels** (Mutate + Validate)
  - Yeni dosya: `platform/kyverno-policies/require-tenant-labels.yaml`
  - haven.io/tenant label inject + validate

- [ ] **2.7 Policy: require-health-probes** (Validate)
  - Yeni dosya: `platform/kyverno-policies/require-health-probes.yaml`
  - Deployment/StatefulSet liveness+readiness zorunlu, Job/CronJob hariç

- [ ] **2.8 ArgoCD ServerSideDiff**
  - Mevcut Application manifest'lere `ServerSideDiff=true` ekle

### Test Planı
- YAML validation: `kubectl apply --dry-run=client -f platform/kyverno-policies/`
- Policy syntax doğru mu: Kyverno CLI (`kyverno test`)
- Architect agent: policy design review
- Tester agent: dry-run + syntax check

### Definition of Done
- [ ] 5 policy YAML syntaktik doğru
- [ ] Kyverno ArgoCD Application manifest hazır
- [ ] ArgoCD ServerSideDiff eklenmiş
- [ ] PR oluşturuldu, merge-ready

---

## Sprint 3: Gitea Internal Git (Per-Tenant Source Code)
**Branch**: `feature/sprint3-gitea-internal-git`
**Durum**: ⏳ Sprint 2 bitmesini bekliyor
**Tahmini**: 2-3 gün
**Bağımlılık**: Sprint 1 merged

### Task'lar

- [ ] **3.1 Gitea HTTPS HTTPRoute**
  - Dosya: `infrastructure/environments/dev/main.tf` — git.{IP}.sslip.io route
  - Certificate SAN'a git hostname ekle

- [ ] **3.2 Gitea Service: Multi-Tenant Org Methods**
  - Dosya: `api/app/services/gitea.py`
  - create_organization(), add_org_member(), create_repo(), list_org_repos(), list_branches(), get_file_tree()

- [ ] **3.3 Tenant Provision'a Gitea Org Ekle**
  - Dosya: `api/app/services/tenant_service.py`
  - _provision_gitea_org() + tenant delete'e org silme

- [ ] **3.4 Application Model: git_provider Field**
  - Dosya: `api/app/models/application.py` — git_provider kolonu
  - Dosya: `api/app/schemas/application.py` — schema güncelle
  - Alembic migration

- [ ] **3.5 Gitea Repo API Endpoints**
  - Yeni dosya: `api/app/routers/gitea_repos.py`
  - GET repos, POST repo, GET branches, GET tree

- [ ] **3.6 Build Pipeline Dual Provider**
  - Dosya: `api/app/services/build_service.py` — clone URL git_provider'a göre

- [ ] **3.7 Gitea Webhook Auto-Deploy**
  - Yeni dosya: `api/app/routers/webhooks.py` (Gitea handler)
  - HMAC-SHA256 signature validation
  - Repo → App mapping + auto build trigger

- [ ] **3.8 UI: Source Code Provider Seçimi**
  - Yeni: `ui/components/GitProviderPicker.tsx`
  - Yeni: `ui/components/GiteaRepoPicker.tsx`
  - Yeni: `ui/components/GiteaFileBrowser.tsx`
  - Güncelle: `ui/app/tenants/[slug]/apps/new/page.tsx` — wizard Step 2

- [ ] **3.9 UI: Git Access Token Yönetimi**
  - Yeni: `api/app/routers/git_tokens.py`
  - Yeni: `ui/app/tenants/[slug]/settings/git-access/page.tsx`

### Test Planı
- Backend: pytest (gitea org CRUD, repo CRUD, webhook, git_provider)
- Frontend: Playwright (provider seçimi, repo browse)
- Lint: ruff + eslint
- Architect agent: API design review
- Tester agent: tüm test suite

### Definition of Done
- [ ] Backend testler yazıldı + geçti
- [ ] Playwright E2E testler yazıldı + geçti
- [ ] Alembic migration çalışıyor
- [ ] PR oluşturuldu, merge-ready

---

## Sprint 4: UI IAM + Kyverno Enforce + Hardening
**Branch**: `feature/sprint4-ui-iam`
**Durum**: ⏳ Sprint 3 bitmesini bekliyor
**Tahmini**: 1-2 gün
**Bağımlılık**: Sprint 3 merged

### Task'lar

- [ ] **4.1 UI Permission Hook**
  - Yeni: `ui/hooks/usePermissions.ts`
  - JWT'den rol çıkarma, canDeploy/canManageServices/canInviteMembers helpers

- [ ] **4.2 PermissionGate Component**
  - Yeni: `ui/components/PermissionGate.tsx`
  - Yetkisiz → children render edilmez

- [ ] **4.3 Role-Based Button Visibility**
  - Deploy/build: developer+
  - Service provision: admin+
  - Üye yönetimi: owner only
  - Tenant delete: owner only

- [ ] **4.4 Akıllı UI Önleme**
  - Registry dropdown: sadece Harbor images
  - Resource tier presets (Kyverno limitlerinin altına düşemez)

- [ ] **4.5 Rate Limiting Per-Endpoint**
  - Dosya: `api/app/main.py`
  - /auth: 20/dk, /build: 10/dk per tenant, /services: 5/dk

- [ ] **4.6 Kyverno Policy: audit → enforce**
  - 5 policy'de `validationFailureAction: Audit` → `Enforce`
  - PolicyException: BuildKit, system workloads

### Test Planı
- Playwright: rol bazlı buton visibility
- Backend: rate limiting testleri
- Architect agent: security review
- Tester agent: tüm test suite

### Definition of Done
- [ ] Playwright E2E testler geçti
- [ ] Backend testler geçti
- [ ] PR oluşturuldu, merge-ready

---

## Cluster Deploy (Tüm Sprint'ler Merge Edildikten Sonra)
**Durum**: ⏳ Sprint 1-4 merged sonrası

- [ ] `tofu init -migrate-state` (local → Hetzner S3)
- [ ] `tofu apply -var-file=terraform.tfvars`
- [ ] Keycloak realm import
- [ ] Kyverno policies apply
- [ ] 15/15 Haven canlı doğrulama
- [ ] Cross-tenant izolasyon testi
- [ ] CLAUDE.md skor güncelle
