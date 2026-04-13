# ArgoCD ApplicationSets — iyziops-root children

`iyziops-root` Application (cloud-init) watches this directory with `recurse: false` and applies every `.yaml` file as a resource. Only ApplicationSet manifests live here — no raw Applications. Cleanup of dependent resources + RBAC lives under `platform/argocd/apps/`.

## Hierarchy

```
iyziops-root (Application, cloud-init-managed, project=iyziops-platform)
  │
  ├── platform-helm         (ApplicationSet, List + RollingSync, Helm charts only)
  │     ├─[ 0] cert-manager           (jetstack v1.20.2)
  │     ├─[ 0] longhorn               (longhorn 1.8.0)
  │     ├─[ 0] kyverno                (kyverno 3.7.1)
  │     └─[ 3/4 FUTURE] observability + data-services (commented placeholders)
  │
  ├── platform-raw          (ApplicationSet, List + RollingSync, raw YAML only)
  │     ├─[-5] platform-ingress       (Gateway + HTTPRoute)
  │     ├─[ 1] cert-manager-config    (ClusterIssuers + wildcard cert)
  │     └─[ 1] kyverno-policies       (5 ClusterPolicy in Audit mode)
  │
  ├── tenant-management     (ApplicationSet, List)
  │     ├─[ 5] iyziops-api            (raw YAML, Deployment in haven-system)
  │     └─[ 5] iyziops-ui             (raw YAML, Deployment in haven-system)
  │
  └── tenants               (ApplicationSet, Git directories + RollingSync 20%)
        └─[10] tenant-{slug} per gitops/tenants/{slug} directory
```

## Sync-wave contract

`platform` uses `strategy: RollingSync` with per-wave gates — each step waits for all Applications labeled `argocd.argoproj.io/sync-wave=<N>` to reach Healthy before moving on. This guarantees strict intra-appset ordering.

Across appsets, ArgoCD does NOT strictly coordinate. Instead, each generated Application has `retry.limit=10` + `selfHeal=true`, so an iyziops-api that tries to sync before cert-manager-config is ready will enter `Progressing`, retry on exponential backoff, and succeed once upstream stabilizes.

On a fresh cluster, expected boot time from `git push main` to all-green:

```
T+0s    root syncs → 3 ApplicationSets created
T+5s    platform wave -5 applied (ingress)
T+60s   platform wave 0 Healthy (cert-manager + longhorn + kyverno controllers)
T+120s  platform wave 1 Healthy (ClusterIssuers + ClusterPolicies)
T+180s  tenant-management wave 5 succeeds on retry (iyziops-api + iyziops-ui)
T+300s  ALL GREEN, zero manual intervention
```

## AppProjects

- `iyziops-platform` — broad access, used by all platform layers. Defined in `infrastructure/modules/rke2-cluster/manifests/argocd-projects.yaml.tpl`.
- `iyziops-tenants` — restricted to `tenant-*` namespaces, no ClusterRole/CRD/Namespace creation. Same template file.

Both AppProjects are created by cloud-init on first master, not managed by ArgoCD itself (to avoid chicken-and-egg).

## How to add a new platform component

1. Edit `platform.yaml` and add a new element under `generators[0].list.elements`:
   - Set `syncWave` to the appropriate phase (use existing waves, or pick 3/4 for observability/data-services)
   - For Helm: set `sourceType: helm`, `repoURL`, `chart`, `targetRevision`, `values` (multiline YAML)
   - For raw YAML: set `sourceType: git`, `path` (relative to repo root)
2. Create the corresponding directory under `platform/argocd/apps/platform/<name>/` with raw manifests (git-path case only)
3. Add the Helm repo URL to `infrastructure/modules/rke2-cluster/manifests/argocd-projects.yaml.tpl` `iyziops-platform.spec.sourceRepos`
4. Commit + push main
5. `kubectl annotate app iyziops-root -n argocd argocd.argoproj.io/refresh=hard --overwrite`

## How to add a new tenant

The iyziops API creates `gitops/tenants/<slug>/` directory when provisioning a tenant. The `tenants` ApplicationSet picks it up automatically on next reconcile (within 3 minutes). No manual ArgoCD interaction required.

## Files

| File | Purpose |
|---|---|
| `platform-helm.yaml` | Helm-chart platform components (operators + future observability/data-services) |
| `platform-raw.yaml` | Raw-YAML platform components (ingress, cert-manager-config, kyverno-policies) |
| `tenant-management.yaml` | iyziops-api + iyziops-ui (iyziops control-plane workloads) |
| `tenants.yaml` | Per-tenant Applications (Git directories generator) |
| `README.md` | This file |

## Non-ArgoCD-managed resources

The following resources are installed by cloud-init BEFORE ArgoCD and are not managed by any appset:
- Gateway API CRDs — installed via `curl | kubectl apply` in master-cloud-init.yaml.tpl (release v1.2.0 experimental channel)
- AppProjects (iyziops-platform, iyziops-tenants) — `argocd-projects.yaml.tpl` manifest
- argocd-repo-secret (GitOps SSH key) — `argocd-repo-secret.yaml.tpl`
- iyziops-root Application itself — `argocd-root-app.yaml.tpl`

These live in `infrastructure/modules/rke2-cluster/manifests/` and are never touched by ArgoCD sync.
