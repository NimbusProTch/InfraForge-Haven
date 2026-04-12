# platform/argocd/appsets

Second tier of the iyziops ArgoCD hierarchy.

```
iyziops-root  (created by cloud-init on first master, sync auto)
  ├─► platform-operators   → watches apps/operators/
  ├─► platform-services    → watches apps/services/
  ├─► platform-ingress     → watches apps/ingress/
  ├─► iyziops-apps         → watches apps/iyziops/
  └─► tenants              → ApplicationSet, generator on gitops/tenants/*
```

Four of the five entries are App-of-Apps child Applications (same Project, recursive directory watch). The fifth is a real ArgoCD `ApplicationSet` because tenants are generated dynamically from the GitOps repo structure: the iyziops API writes `gitops/tenants/<slug>/` subdirectories as tenants are provisioned, and the ApplicationSet auto-creates a per-tenant Application scoped to the `iyziops-tenants` AppProject.

Next sprint will replace the four App-of-Apps entries with real ApplicationSets once each child directory has at least one real workload.
