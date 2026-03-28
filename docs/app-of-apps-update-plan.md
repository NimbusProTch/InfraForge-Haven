# App-of-Apps Update Plan (Sprint I-4)

## Current State

`platform/argocd/app-of-apps.yaml` contains a single ArgoCD `Application` that
watches two source paths:

1. `platform/argocd/apps` — platform-level Applications (haven-api, haven-ui)
2. `platform/argocd/applicationsets` — **global** ApplicationSets (haven-tenant-apps, haven-tenant-services)

The global ApplicationSets (`tenant-apps.yaml`, `tenant-services.yaml`) scan **all**
tenants at once:
```
gitops/tenants/*/*          → apps
gitops/tenants/*/services/* → services
```

## Problem

A single ApplicationSet covering all tenants means:
- No per-tenant RBAC on sync operations
- Cannot set different sync policies per tenant (e.g. manual sync for prod tenants)
- ApplicationSet name/label space not isolated per tenant

## Target State (per-tenant ApplicationSets)

Each tenant gets its own pair of ApplicationSets:
- `appset-{slug}` — watches `gitops/tenants/{slug}/*` (excluding `services/`)
- `svcset-{slug}` — watches `gitops/tenants/{slug}/services/*`

These are rendered by `platform/templates/tenant-appset-generator.py` and committed
to `platform/argocd/applicationsets/` as:
- `tenant-{slug}-apps.yaml`
- `tenant-{slug}-services.yaml`

## Migration Steps

### Step 1 — Keep global ApplicationSets in place (no downtime)
The existing `haven-tenant-apps` and `haven-tenant-services` global ApplicationSets
remain active. Do not delete them yet.

### Step 2 — Generate per-tenant ApplicationSets
For each existing tenant:
```bash
# From project root
python platform/templates/tenant-appset-generator.py \
  --tenant gemeente-utrecht \
  --revision main \
  --both \
  --output-dir platform/argocd/applicationsets/
```

Commit the generated files:
```bash
git add platform/argocd/applicationsets/tenant-*.yaml
git commit -m "feat: add per-tenant ApplicationSets for existing tenants"
git push
```

ArgoCD app-of-apps will pick up the new files from
`platform/argocd/applicationsets/` and apply them automatically (it watches the
whole directory).

### Step 3 — Verify parallel operation
After ArgoCD syncs, both the global and per-tenant ApplicationSets will exist.
Check that Applications are not duplicated:

```bash
kubectl get applications -n argocd | grep <tenant-slug>
```

If duplicates appear, scale down the old global ApplicationSet controller by
patching it to use a selector that excludes already-migrated tenants:

```yaml
# In tenant-apps.yaml (global) — add exclusion
generators:
  - git:
      directories:
        - path: "gitops/tenants/*/*"
        - path: "gitops/tenants/gemeente-utrecht/*"
          exclude: true   # <-- exclude migrated tenant
```

### Step 4 — Update app-of-apps.yaml
Once all tenants are migrated and verified, **remove the global ApplicationSets**
from the repo and update `app-of-apps.yaml` if any explicit references exist.

**Do NOT edit app-of-apps.yaml during parallel operation** — it already watches
the entire `platform/argocd/applicationsets/` directory, so new files are auto-picked-up.

### Step 5 — Remove global ApplicationSets
```bash
kubectl delete applicationset haven-tenant-apps haven-tenant-services -n argocd
git rm platform/argocd/applicationsets/tenant-apps.yaml
git rm platform/argocd/applicationsets/tenant-services.yaml
git commit -m "feat: remove global ApplicationSets; all tenants use per-tenant sets"
git push
```

## New Tenant Provisioning

When the Platform API creates a new tenant (`POST /api/v1/tenants`), the tenant
service should call the generator as part of the provisioning flow:

```python
# In api/app/services/tenant_service.py (Sprint I-5)
from platform.templates import tenant_appset_generator

app_yaml = tenant_appset_generator.render_app_appset(tenant_slug)
svc_yaml = tenant_appset_generator.render_svc_appset(tenant_slug)
# enqueue via GitQueueService
```

Or invoke the generator script via subprocess if the API runs in a container
without direct access to the platform/templates/ directory.

## Naming Convention

| Resource | Name pattern | Example |
|----------|-------------|---------|
| App ApplicationSet | `appset-{slug}` | `appset-gemeente-utrecht` |
| Service ApplicationSet | `svcset-{slug}` | `svcset-gemeente-utrecht` |
| Application (app) | `{slug}-{app-slug}` | `gemeente-utrecht-my-api` |
| Application (service) | `svc-{slug}-{svc-name}` | `svc-gemeente-utrecht-postgres` |

## Labels

All resources carry:
```yaml
haven.io/managed: "true"
haven.io/tenant: "<tenant-slug>"
haven.io/type: "tenant-apps" | "tenant-services"
```

This enables easy listing and RBAC scoping:
```bash
kubectl get applications -n argocd -l haven.io/tenant=gemeente-utrecht
```
