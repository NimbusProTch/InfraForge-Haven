# Haven GitOps

This directory contains Helm values for tenant applications.
ArgoCD ApplicationSet watches this directory and syncs resources automatically.

## Directory Structure

```
tenants/
└── {tenant-slug}/
    ├── {app-slug}/
    │   └── values.yaml       # haven-app chart values (API-generated)
    └── {app-slug-2}/
        └── values.yaml
```

## How It Works

1. User creates an app via the Haven API
2. `GitOpsScaffold.scaffold_app()` writes initial `values.yaml` to Gitea
3. ArgoCD `haven-tenant-apps` ApplicationSet detects the new directory
4. Creates an ArgoCD Application:
   - Chart source: `charts/haven-app` (from GitHub)
   - Values source: `tenants/{tenant}/{app}/values.yaml` (from Gitea)
5. ArgoCD syncs → Deployment, Service, HTTPRoute, HPA created in `tenant-{slug}` namespace

## On Build

1. API builds Docker image via BuildKit → pushes to Harbor
2. `GitOpsService.write_app_values()` updates `values.yaml` with new image tag
3. ArgoCD auto-syncs → rolling update

## On Config Update

1. User updates env vars, replicas, resources via API
2. Git Worker picks up the change from Redis queue
3. Updates `values.yaml` in Gitea
4. ArgoCD auto-syncs (selfHeal: true)

## What Is NOT Here

- **Namespaces** — created via K8s API (`TenantService.provision()`)
- **Managed services (DB, Redis, RabbitMQ)** — provisioned via Everest REST API / K8s CRD
- **Kustomization files** — ApplicationSet uses directory-based discovery, not kustomize

## Configuration

The Haven API requires `GITEA_ADMIN_TOKEN` (or `GITOPS_GITHUB_TOKEN`)
stored in the `haven-api-secrets` Kubernetes Secret.
`GITOPS_REPO_URL` must point to the Gitea haven-gitops repo.
