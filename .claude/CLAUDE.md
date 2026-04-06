# Haven Platform — Claude Code Project Memory

> This file is loaded by Claude Code at the start of every session.
> Source of truth: root `CLAUDE.md`. This file extends it with architectural decisions.

---

## What Is Haven?

Haven is a Haven-compliant self-service DevOps platform (PaaS) for 342 Dutch municipalities.
It provides a Heroku/Railway-like experience on top of Kubernetes, guaranteeing EU data
sovereignty via Hetzner (dev) and Cyso Cloud Amsterdam (prod). The full pipeline is:
**UI → API → Redis Queue → Gitea GitOps repo → ArgoCD → RKE2 K8s cluster**.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| IaC | OpenTofu (Terraform fork, CNCF) |
| Cluster Mgmt | Rancher + RKE2 (CIS hardened, CNCF certified) |
| CNI | Cilium (eBPF, Gateway API, Hubble) |
| Ingress | Cilium Gateway API (HTTPRoute) |
| Storage | Longhorn (CNCF, RWX) |
| TLS | Cert-Manager + Let's Encrypt |
| DNS | Cloudflare + External-DNS |
| Auth | Keycloak (realm-per-tenant) |
| GitOps | ArgoCD (ApplicationSet per tenant) |
| Git Server | Gitea / Forgejo (self-hosted, tenant repos) |
| App Build | BuildKit + Nixpacks (K8s-native, 5x faster than Kaniko) |
| Registry | Harbor (self-hosted, Trivy scan) |
| DB (managed) | CNPG (PostgreSQL), Percona Everest (MySQL/MongoDB), Redis Operator, RabbitMQ Operator |
| Secrets | HashiCorp Vault + External Secrets Operator |
| Backup | MinIO S3 (per-tenant bucket, PITR) |
| Monitoring | Grafana + Loki + Mimir + Hubble UI |
| Queue | Redis (git write serialization) |
| Backend | Python 3.12 / FastAPI |
| Frontend | Next.js 14 / shadcn/ui |
| Dev Cloud | Hetzner (Falkenstein + Nuremberg) |
| Prod Cloud | Cyso Cloud / Leafcloud (Amsterdam, Phase 2+) |

---

## Repository Structure

```
haven-platform/
├── CLAUDE.md                    # Root project memory (primary)
├── .claude/CLAUDE.md            # This file (architecture extension)
├── INFRA_SPRINT_PLAN_V2.md      # Current sprint plan (10 sprints)
├── SPRINT_PLAN.md               # App-layer sprint plan
├── architecture-diagram.html    # Interactive architecture diagram
├── infrastructure/              # OpenTofu IaC
│   ├── modules/
│   │   ├── rancher-cluster/     # RKE2 cluster + Helm value templates
│   │   ├── hetzner-infra/       # VM, Network, LB, Firewall
│   │   └── dns/                 # Cloudflare DNS
│   └── environments/
│       ├── dev/                 # Hetzner dev environment
│       └── production/          # Cyso/NL production (Phase 2+)
├── platform/
│   └── argocd/
│       ├── app-of-apps.yaml     # Root ArgoCD Application
│       ├── apps/                # Per-service Application manifests
│       └── templates/           # ApplicationSet templates (per tenant)
├── charts/                      # Internal Helm charts
│   ├── haven-pg/                # CNPG wrapper (PostgreSQL)
│   ├── haven-mysql/             # Percona XtraDB wrapper
│   ├── haven-mongodb/           # Percona MongoDB wrapper
│   ├── haven-redis/             # Redis Operator wrapper
│   └── haven-rabbitmq/          # RabbitMQ Operator wrapper
├── api/                         # Platform API (FastAPI)
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── models/              # SQLAlchemy 2.0 async models
│       ├── schemas/             # Pydantic v2 schemas
│       ├── routers/             # API route handlers
│       ├── services/            # Business logic
│       │   ├── gitea.py         # Gitea HTTP API wrapper
│       │   ├── gitops_scaffold.py  # Repo scaffold on tenant/app create
│       │   ├── gitops_values.py    # values.yaml CRUD
│       │   ├── git_queue.py        # Redis FIFO queue for git writes
│       │   ├── argocd.py           # ArgoCD API wrapper (sync, history, rollback)
│       │   ├── vault.py            # HashiCorp Vault API wrapper
│       │   ├── managed_db.py       # DB provision/deprovision
│       │   └── backup.py           # DB backup/restore
│       ├── workers/
│       │   └── git_writer.py    # Single-worker git commit processor
│       ├── templates/gitops/    # Jinja2 templates for values.yaml etc.
│       ├── k8s/                 # Kubernetes client wrapper
│       └── auth/                # Keycloak JWT verification
├── ui/                          # Portal (Next.js 14)
│   └── app/
│       ├── apps/[id]/
│       │   ├── config/          # Env vars, replicas, resources
│       │   └── deployments/     # Sync, history, rollback
│       └── tenants/[id]/
│           └── services/        # Managed DB provision UI
├── gitops/                      # haven-gitops repo mirror
│   └── tenants/
│       └── {slug}/
│           ├── kustomization.yaml
│           └── apps/
│               └── {app-slug}/
│                   └── values.yaml
├── automation/                  # Claude Code runner + Telegram bot
└── docs/
```

---

## Architectural Decisions

### 1. GitOps-First: Everything Through Git
All state changes flow through Gitea → ArgoCD. Direct `kubectl apply` only for
bootstrapping. Application state lives in `gitops/tenants/{slug}/apps/{app}/values.yaml`.

### 2. Queue-Based Git Writer (Conflict Prevention)
All git commits go through a single Redis FIFO queue worker (`workers/git_writer.py`).
This prevents concurrent commit conflicts when multiple users modify values simultaneously.
Dead-letter queue (`haven:git:dlq`) captures failures after 3 retries.

### 3. ApplicationSet per Tenant
Each tenant gets its own ArgoCD `ApplicationSet` pointing to `gitops/tenants/{slug}/apps/*`.
ArgoCD auto-discovers new apps by watching the git directory structure — no API call needed
when deploying a new app.

### 4. Vault + External Secrets for Sensitive Vars
Non-sensitive env vars → values.yaml in Gitea (plaintext, version-controlled).
Sensitive vars (DB passwords, API keys) → HashiCorp Vault → ESO `ExternalSecret` CRD →
K8s Secret. UI shows a `🔒` toggle to mark a var as sensitive.

### 5. Managed DB via Helm Charts
Each DB type has a thin Helm wrapper in `charts/`. Provisioning a DB = pushing a new
`values.yaml` to the GitOps repo → ArgoCD deploys the chart → CNPG/Percona creates the DB.
Connection string auto-injected into the app's `values.yaml` as `DATABASE_URL`.

### 6. BuildKit > Kaniko
BuildKit is ~5x faster than Kaniko due to parallel layer build and intelligent caching.
BuildKit runs as a Deployment in `haven-builds` namespace, accepts `buildctl` job submissions.
Nixpacks handles auto-detection of language/framework and start command generation.

### 7. Multi-Tenancy: 5-Layer Isolation
1. Namespace (`tenant-{slug}`)
2. CiliumNetworkPolicy (L7 isolation)
3. ResourceQuota (CPU/RAM/Disk limits)
4. RBAC (tenant admin scoped to own namespace)
5. Keycloak realm per tenant

### 8. Two-Provider Rancher Pattern
`rancher2.bootstrap` for initial Rancher login, `rancher2.admin` for cluster operations.
`rancher2_cluster_sync` (native, Go-based) with `wait_catalogs=true` + `state_confirm=3`
for reliable cluster readiness detection.

### 9. Backup: MinIO per Tenant
Each tenant gets a dedicated MinIO bucket (`backups-{slug}`). CNPG handles WAL archiving
for PITR. Scheduled backups run daily at 02:00 UTC. On-demand backup via API endpoint.

### 10. Build Log Streaming via SSE
Build logs stream from K8s Pod logs via Server-Sent Events. ANSI escape codes rendered in
browser via `ansi-to-html`. Hard timeout: 10 minutes. No-output timeout: 2 minutes.

---

## GitOps Flow

```
User (Browser)
    │
    ▼
Haven UI (Next.js)
    │  REST / SSE
    ▼
Haven API (FastAPI)
    │
    ├─► Redis Queue (FIFO)
    │       │
    │       ▼
    │   Git Writer Worker
    │       │  git push
    │       ▼
    │   Gitea (haven-gitops repo)
    │       │  webhook / poll
    │       ▼
    │   ArgoCD ApplicationSet
    │       │  kubectl apply
    │       ▼
    │   RKE2 K8s Cluster
    │       ├── Pods (app containers)
    │       ├── Services + HTTPRoutes
    │       ├── CNPG / Everest DBs
    │       └── K8s Secrets (from Vault via ESO)
    │
    └─► Direct K8s API (build jobs, log streaming, status checks)
```

---

## Customer Journey (Summary)

1. **Login** → Keycloak (OIDC) → tenant scoped JWT
2. **Create app** → GitHub repo select → POST /apps → GitOps scaffold → ArgoCD AppSet
3. **Deploy** → Push to GitHub → webhook → BuildKit job → Harbor push → values.yaml image tag update → ArgoCD sync → Pod running
4. **Configure** → UI env var editor → PATCH /apps/{id}/env-vars → git queue → values.yaml update → ArgoCD auto-sync
5. **Monitor** → Grafana/Loki dashboards per app, build logs via SSE
6. **Rollback** → Deployments tab → select revision → POST /apps/{id}/rollback → ArgoCD rollback to git revision

---

## Coding Standards

### Python / FastAPI
- Python 3.12+, type hints mandatory everywhere
- Pydantic v2 (`model_validator`, `field_validator`)
- SQLAlchemy 2.0 async (`mapped_column`, `DeclarativeBase`)
- Ruff linter + formatter (`line-length = 120`)
- Import order: stdlib → third-party → local
- Router files: `routers/{resource}.py`
- Service files: `services/{domain}.py`
- Test files: `tests/test_{module}.py`

### TypeScript / Next.js
- Next.js 14 App Router (no Pages Router)
- shadcn/ui components (do not reinvent)
- `export const dynamic = "force-dynamic"` on pages with search params
- Suspense boundary required for `useSearchParams()`
- Fetch: native `fetch` with `cache: 'no-store'` for API calls

### OpenTofu / HCL
- Module structure: `modules/{provider}-{resource}/`
- Environment structure: `environments/{env}/`
- Naming: `{resource_type}-{environment}-{purpose}`
- Helm templates: inside module `templates/*.yaml.tpl`
- No bash scripts in `local-exec` — use `rancher2_*` resources or `ssh_resource`

### Git
- Conventional commits: `feat:`, `fix:`, `infra:`, `docs:`
- Code comments in English, documentation in Turkish
- One task = one commit

---

## Definition of Done (ZORUNLU — İHLAL EDİLEMEZ)

Bir task "done" sayılması için aşağıdaki TÜM adımlar tamamlanmış olmalı.
Herhangi biri eksikse "done" denilemez.

### Backend Değişiklikleri

1. **Kod yazıldı** — feature/fix implementasyonu tamamlandı
2. **Yeni testler yazıldı** — test count artmalı, her yeni feature/fix için test olmalı
3. **Tüm testler geçti** — `pytest tests/ -q` ile lokal olarak doğrulandı
4. **Lint + Format geçti** — `ruff check .` + `ruff format --check .` (CI ile aynı)
5. **PR açıldı** — feature branch'ten main'e PR oluşturuldu
6. **CI green** — GitHub Actions: Lint ✅, Test ✅, Build & Push ✅, Update Manifest ✅
7. **Architect agent review** — Kod kalitesi, mimari, güvenlik inceledi. Blocking bug varsa düzeltildi, tekrar review.
8. **Tester agent review** — Testleri çalıştırdı, coverage kontrol etti, approve etti.
9. **PR merge edildi** — main branch'e merge
10. **Cluster'a deploy oldu** — ArgoCD sync, pod'lar yeni image ile Running doğrulandı:
    ```bash
    KC=infrastructure/environments/dev/kubeconfig
    kubectl --kubeconfig=$KC get pods -n haven-system -l app=haven-api \
      -o jsonpath='{.items[0].spec.containers[0].image}'
    # Image tag merge commit SHA ile eşleşmeli
    ```
11. **API erişilebilir** — `curl https://api.46.225.42.2.sslip.io/api/docs` → 200
12. **Yeni endpoint'ler doğrulandı** — OpenAPI spec'te yeni endpoint'ler görünüyor

### Frontend (UI) Değişiklikleri

1-9 aynı (lint: `npm run lint`, build: `npm run build`, test: `npm run test`)
10. **UI cluster'a deploy oldu** — haven-ui pod yeni image ile Running:
    ```bash
    kubectl --kubeconfig=$KC get pods -n haven-system -l app=haven-ui \
      -o jsonpath='{.items[0].spec.containers[0].image}'
    ```
11. **Browser testi** — Gerçek bir kullanıcı gibi browser'dan test et:
    - Değişen sayfayı aç, tıkla, form doldur, submit et
    - Network tab'da API çağrılarını kontrol et (CORS hata yok, 401 yok)
    - Console'da JS error yok
    - Mobile responsive kontrol et
12. **Playwright E2E** — Otomatik test yazıldı ve geçti (`npx playwright test`)

### Review Agent Kuralları

- **Her PR'da architect + tester agent çalıştırılacak** — atlama yok
- Architect: kod review, mimari, güvenlik, blocking bug tespiti
- Tester: testleri gerçekten çalıştırır, coverage kontrol eder, pass/fail rapor eder
- **İkisi de approve etmeden merge yasak** (self-approval GitHub'da çalışmıyorsa, her ikisinin de "approve" dediğini doğrula)
- Blocking bug bulunursa: düzelt → tekrar review → approve → merge

### Kritik Kurallar

- **CI geçmesi YETERLİ DEĞİL** — Cluster deploy + pod running + API/UI doğrulama zorunlu
- **Unit test geçmesi YETERLİ DEĞİL** — Browser'dan görsel doğrulama (UI) veya curl ile endpoint doğrulama (API) zorunlu
- **"Yazdım, merge ettim" YETERLİ DEĞİL** — Deploy oldu mu? Pod yeni image mı? Erişilebilir mi?

**ArgoCD otomatik sync etmiyorsa** hard refresh:
```bash
KC=infrastructure/environments/dev/kubeconfig
kubectl --kubeconfig=$KC patch application haven-api -n argocd --type merge \
  -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
```

---

## Test Commands

```bash
# API unit tests
cd api && poetry run pytest tests/ -v

# API with coverage
cd api && poetry run pytest tests/ --cov=app --cov-report=term-missing

# Lint + format check
cd api && poetry run ruff check . && poetry run ruff format --check .

# Frontend type check
cd ui && npm run type-check

# Frontend lint
cd ui && npm run lint

# Frontend build check
cd ui && npm run build

# OpenTofu plan (dev)
cd infrastructure/environments/dev && tofu plan -var-file=terraform.tfvars

# K8s cluster health
kubectl get nodes -o wide
kubectl get pods -A | grep -v Running | grep -v Completed

# ArgoCD app status
kubectl get applications -n argocd

# CNPG cluster status
kubectl get cluster -A
```
