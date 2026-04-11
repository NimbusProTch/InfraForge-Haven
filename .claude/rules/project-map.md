# Proje Haritası — Her Şey Nerede?

Bu dosya her session'da okunur. Yeni session açıldığında hiçbir şey sorma — buraya bak.

## Repo Yapısı

```
haven-platform/
├── CLAUDE.md                          # Ana proje hafızası (root, tek kaynak)
├── .claude/
│   ├── CLAUDE.md                      # Mimari detaylar
│   ├── settings.json                  # İzinler
│   ├── rules/                         # ⭐ Her session otomatik okunur
│   ├── commands/                      # /slash komutları
│   └── agents/                        # architect.md, tester.md
│
├── api/                               # Backend (FastAPI)
│   ├── app/
│   │   ├── main.py                    # FastAPI app entry
│   │   ├── config.py                  # Settings (env vars)
│   │   ├── models/                    # SQLAlchemy modeller
│   │   ├── schemas/                   # Pydantic v2 schemas
│   │   ├── routers/                   # API endpoint'leri
│   │   ├── services/                  # Business logic
│   │   │   ├── build_service.py       # BuildKit job oluşturma
│   │   │   ├── tenant_service.py      # Tenant lifecycle (namespace, quota, CNP, RBAC)
│   │   │   ├── gitea.py               # Gitea HTTP API wrapper
│   │   │   ├── gitops_scaffold.py     # GitOps repo scaffold
│   │   │   ├── argocd.py              # ArgoCD sync/rollback
│   │   │   ├── managed_service.py     # DB provision (Everest/CRD)
│   │   │   └── vault.py               # Vault API wrapper
│   │   ├── k8s/                       # Kubernetes client wrapper
│   │   └── auth/                      # JWT + RBAC (jwt.py, rbac.py)
│   ├── tests/                         # ⭐ BACKEND TESTLER BURDA (71 dosya, ~1185 test)
│   │   └── test_{module}.py           # Test dosya pattern
│   ├── pyproject.toml                 # Dependencies
│   └── Dockerfile
│
├── ui/                                # Frontend (Next.js 14)
│   ├── app/                           # App Router pages
│   ├── components/                    # React components
│   ├── lib/                           # API client, auth, utils
│   ├── package.json
│   └── Dockerfile
│
├── infrastructure/                    # OpenTofu IaC
│   ├── modules/
│   │   ├── rancher-cluster/           # RKE2 cluster + Helm templates
│   │   │   └── templates/             # cilium-values, longhorn-values, cloud-init
│   │   ├── hetzner-infra/             # VM, Network, LB, Firewall
│   │   └── dns/                       # Cloudflare
│   └── environments/
│       ├── dev/                       # ⭐ ANA INFRA BURDA
│       │   ├── main.tf                # Tüm resource'lar (1300+ satır)
│       │   ├── variables.tf           # Tüm variable'lar
│       │   ├── backend.tf             # Hetzner S3 remote state
│       │   ├── providers.tf           # rancher2 provider
│       │   ├── terraform.tfvars       # ⚠️ GİTİGNORED — secret'lar
│       │   ├── helm-values/           # Longhorn, monitoring, logging
│       │   └── templates/             # cloud-init templates
│       └── production/                # Cyso/NL (Phase 2+)
│
├── platform/                          # ArgoCD + Kyverno + Manifests
│   ├── argocd/
│   │   ├── app-of-apps.yaml
│   │   └── apps/                      # haven-api, haven-ui, kyverno, kyverno-policies
│   ├── kyverno-policies/              # ⭐ 5 ClusterPolicy YAML
│   ├── manifests/
│   │   ├── haven-api/                 # deployment, clusterrole, service
│   │   └── haven-ui/                  # deployment, service
│   └── base/                          # Namespace, RBAC templates
│
├── charts/                            # Helm charts (haven-pg, haven-mysql, etc.)
├── keycloak/                          # haven-realm.json, bootstrap scripts
├── gitops/                            # haven-gitops repo mirror (tenant manifests)
├── runner/                            # ⭐ CI runner IaC (standalone tofu)
│   └── main.tf                        # Hetzner CX23 runner
├── docs/
│   ├── sprints/                       # Sprint planları
│   │   └── SPRINT_BACKLOG.md          # Aktif sprint task'ları
│   └── haven-compliance/              # Compliance raporları
├── tests/                             # Playwright E2E testler
├── scripts/                           # Bootstrap, migration scripts
└── .github/workflows/                 # ⭐ CI/CD pipeline'lar
    ├── api-ci.yml                     # Lint → Test → Build → Push
    ├── ui-ci.yml                      # Lint → Build → Push
    └── code-quality.yml               # bandit, vulture, semgrep, tflint
```

## CI/CD
- **Runner**: Self-hosted Hetzner CX23 (46.225.154.1), 3 paralel instance
- **Label**: `runs-on: [self-hosted, haven]`
- **PostgreSQL**: docker run step (service container değil)
- **Workflow'lar**: api-ci.yml, ui-ci.yml, code-quality.yml

## Test Konumları
| Tip | Konum | Komut |
|-----|-------|-------|
| Backend unit | `api/tests/test_*.py` | `cd api && pytest tests/ -q` |
| Backend lint | `api/` | `cd api && ruff check . && ruff format --check .` |
| Frontend lint | `ui/` | `cd ui && npm run lint` |
| Frontend build | `ui/` | `cd ui && npm run build` |
| Playwright E2E | `tests/` | `npx playwright test` |
| IaC validate | `infrastructure/` | `cd infrastructure/environments/dev && tofu validate` |

## Cluster Erişimi
- **Kubeconfig**: `infrastructure/environments/dev/kubeconfig`
- **API**: `https://api.46.225.42.2.sslip.io/api/docs`
- **ArgoCD**: argocd namespace
- **Keycloak**: `http://localhost:8080` (port-forward)
- **Gitea**: `http://localhost:3030` (port-forward)
- **Harbor**: `http://harbor.46.225.42.2.sslip.io`

## Agents
| Agent | Dosya | Ne Yapar | Ne Zaman |
|-------|-------|----------|----------|
| Architect | `.claude/agents/architect.md` | PR review (kod, güvenlik, mimari) | Her PR'dan önce |
| Tester | `.claude/agents/tester.md` | Test çalıştır, count doğrula | Her kod değişikliğinde |

## Commands (/slash)
| Komut | Ne Yapar |
|-------|----------|
| `/deep-dive` | Multi-agent araştırma + gap raporu |
| `/haven-check` | 15/15 compliance doğrulama |
| `/security-audit` | Tam güvenlik taraması |
| `/sprint-plan` | Sprint planı oluştur |
| `/sprint` | Sprint execution checklist |
