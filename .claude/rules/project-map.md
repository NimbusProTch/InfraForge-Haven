# Project Map — Where Is Everything?

This file is read every session. Never ask "where is X" — look here.

## Repository Structure

```
haven-platform/
├── CLAUDE.md                          # Main project memory (Turkish)
├── .claude/
│   ├── CLAUDE.md                      # Architecture decisions (English)
│   ├── settings.json                  # Permissions
│   ├── rules/                         # ⭐ Auto-loaded every session
│   ├── commands/                      # /slash commands
│   ├── agents/                        # architect, tester sub-agents
│   └── skills/                        # Multi-file skills
│
├── api/                               # Backend (FastAPI)
│   ├── app/
│   │   ├── main.py                    # FastAPI entry point
│   │   ├── config.py                  # Settings (env vars)
│   │   ├── models/                    # SQLAlchemy models
│   │   ├── schemas/                   # Pydantic v2 schemas
│   │   ├── routers/                   # API endpoints
│   │   ├── services/                  # Business logic
│   │   │   ├── build_service.py       # BuildKit job creation
│   │   │   ├── tenant_service.py      # Tenant lifecycle
│   │   │   ├── gitea.py               # Gitea API wrapper
│   │   │   ├── argocd.py              # ArgoCD sync/rollback
│   │   │   ├── managed_service.py     # DB provisioning
│   │   │   └── vault.py               # Vault API wrapper
│   │   ├── k8s/                       # Kubernetes client
│   │   └── auth/                      # JWT + RBAC
│   ├── tests/                         # ⭐ BACKEND TESTS (71 files, ~1185 tests)
│   │   └── test_{module}.py
│   ├── pyproject.toml
│   └── Dockerfile
│
├── ui/                                # Frontend (Next.js 14)
│   ├── app/                           # App Router pages
│   ├── components/                    # React components
│   ├── lib/                           # API client, auth, utils
│   └── package.json
│
├── infrastructure/                    # OpenTofu IaC
│   ├── modules/                       # Reusable modules
│   │   ├── rancher-cluster/           # RKE2 + Helm templates
│   │   └── hetzner-infra/             # VM, Network, LB, Firewall
│   └── environments/
│       └── dev/                       # ⭐ MAIN INFRA CONFIG
│           ├── main.tf                # All resources (1300+ lines)
│           ├── variables.tf           # All variables
│           ├── backend.tf             # Hetzner S3 remote state
│           ├── terraform.tfvars       # ⚠️ GITIGNORED secrets
│           └── helm-values/           # Longhorn, monitoring, etc.
│
├── platform/                          # ArgoCD + Kyverno + Manifests
│   ├── argocd/apps/                   # ArgoCD Applications
│   ├── kyverno-policies/              # ⭐ 5 ClusterPolicy YAMLs
│   └── manifests/                     # haven-api, haven-ui deployments
│
├── charts/                            # Internal Helm charts
├── keycloak/                          # haven-realm.json, bootstrap scripts
├── gitops/                            # haven-gitops repo mirror
├── runner/                            # ⭐ CI runner IaC (standalone)
│   └── main.tf
├── docs/
│   └── sprints/                       # Sprint plans + backlog
├── tests/                             # Playwright E2E tests
├── scripts/                           # Bootstrap, migration scripts
└── .github/workflows/                 # ⭐ CI/CD pipelines
    ├── api-ci.yml                     # Lint → Test → Build → Push
    ├── ui-ci.yml                      # Lint → Build → Push
    └── code-quality.yml               # bandit, semgrep, tflint
```

## CI/CD
- **Runner**: Self-hosted Hetzner CX23 (46.225.154.1), 3 parallel instances
- **Labels**: `runs-on: [self-hosted, haven]`
- **PostgreSQL for tests**: docker run step (NOT service container)

## Test Locations
| Type | Location | Command |
|------|----------|---------|
| Backend unit | `api/tests/test_*.py` | `cd api && pytest tests/ -q` |
| Backend lint | `api/` | `cd api && ruff check . && ruff format --check .` |
| Frontend lint | `ui/` | `cd ui && npm run lint` |
| Frontend build | `ui/` | `cd ui && npm run build` |
| Playwright E2E | `tests/` | `npx playwright test` |
| IaC validate | `infrastructure/` | `tofu validate` |

## Cluster Access
- **Kubeconfig**: `infrastructure/environments/dev/kubeconfig`
- **API docs**: `https://api.46.225.42.2.sslip.io/api/docs`
- **Harbor**: `http://harbor.46.225.42.2.sslip.io`

## Agents
| Agent | File | Purpose | When |
|-------|------|---------|------|
| Architect | `.claude/agents/architect.md` | PR review | Before every merge |
| Tester | `.claude/agents/tester.md` | Run tests, verify count | Every code change |

## Commands
| Command | Purpose |
|---------|---------|
| `/deep-dive` | Multi-agent research + gap report |
| `/haven-check` | 15/15 compliance verification |
| `/security-audit` | Full security scan |
| `/sprint-plan` | Create sprint plan after deep-dive |
| `/sprint` | Sprint execution checklist |
