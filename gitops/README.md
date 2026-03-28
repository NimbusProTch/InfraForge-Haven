# Haven GitOps

This directory contains Helm values for tenant applications and managed services.
ArgoCD ApplicationSet watches this directory and syncs resources automatically.

## Directory Structure

```
gitops/
└── tenants/
    └── {tenant-slug}/
        ├── {app-slug}/
        │   └── values.yaml       # haven-app chart values (API-generated)
        └── services/
            └── {service-name}/
                └── values.yaml   # haven-managed-service chart values (API-generated)
```

## How It Works

1. User deploys an app via the Haven UI
2. API builds the Docker image and pushes to Harbor
3. API calls `GitOpsService.write_app_values()` which:
   - Clones this repo (or pulls latest)
   - Writes `gitops/tenants/{tenant}/{app}/values.yaml`
   - Commits and pushes to `feature/platform-v2`
4. ArgoCD `haven-tenant-apps` ApplicationSet detects the new directory
5. Creates an ArgoCD Application pointing to `charts/haven-app` with the values file
6. ArgoCD syncs → Deployment, Service, HTTPRoute, HPA created in `tenant-{slug}` namespace

## Configuration

The Haven API requires `GITOPS_GITHUB_TOKEN` (GitHub PAT with repo write access)
stored in the `haven-api-secrets` Kubernetes Secret.

Charts are in `charts/haven-app` and `charts/haven-managed-service`.
