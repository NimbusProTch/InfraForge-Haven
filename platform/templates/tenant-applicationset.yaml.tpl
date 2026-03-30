{#
  Jinja2 template: ArgoCD ApplicationSet for a single tenant's apps.

  Variables:
    tenant_slug       — e.g. "gemeente-utrecht"
    gitops_repo_url   — Gitea internal URL for haven-gitops repo
    chart_repo_url    — GitHub URL for Helm charts (InfraForge-Haven repo)
    target_revision   — e.g. "main"
    chart_path        — path to the haven-app Helm chart, e.g. "charts/haven-app"

  Gitea repo structure: tenants/{tenant_slug}/{app_slug}/values.yaml
  Path segments: [0]=tenants [1]=tenant_slug [2]=app_slug

  Naming convention:
    ApplicationSet name: appset-{tenant_slug}
    Application name:    {tenant_slug}-{app_slug}
    Destination NS:      tenant-{tenant_slug}
#}
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: appset-{{ tenant_slug }}
  namespace: argocd
  labels:
    haven.io/managed: "true"
    haven.io/tenant: "{{ tenant_slug }}"
    haven.io/type: "tenant-apps"
spec:
  goTemplate: true
  goTemplateOptions: ["missingkey=error"]
  generators:
    - git:
        repoURL: {{ gitops_repo_url }}
        revision: {{ target_revision }}
        directories:
          - path: "tenants/{{ tenant_slug }}/*"
          - path: "tenants/{{ tenant_slug }}/services"
            exclude: true
          - path: "tenants/{{ tenant_slug }}/services/*"
            exclude: true
  template:
    metadata:
      # path.segments: [0]=tenants [1]=tenant_slug [2]=app_slug
      name: "{{ tenant_slug }}-{% raw %}{{ index .path.segments 2 }}{% endraw %}"
      namespace: argocd
      labels:
        haven.io/managed: "true"
        haven.io/tenant: "{{ tenant_slug }}"
        haven.io/app: "{% raw %}{{ index .path.segments 2 }}{% endraw %}"
      finalizers:
        - resources-finalizer.argocd.argoproj.io
    spec:
      project: default
      sources:
        - repoURL: {{ chart_repo_url }}
          targetRevision: {{ target_revision }}
          path: "{{ chart_path }}"
          helm:
            valueFiles:
              - "$values/{% raw %}{{ .path.path }}{% endraw %}/values.yaml"
        - repoURL: {{ gitops_repo_url }}
          targetRevision: {{ target_revision }}
          ref: values
      destination:
        server: https://kubernetes.default.svc
        namespace: "tenant-{{ tenant_slug }}"
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=false
          - ServerSideApply=true
        retry:
          limit: 3
          backoff:
            duration: 5s
            factor: 2
            maxDuration: 3m
