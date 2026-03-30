{#
  Jinja2 template: ArgoCD ApplicationSet for a single tenant's managed services.

  Variables:
    tenant_slug       — e.g. "gemeente-utrecht"
    gitops_repo_url   — Gitea internal URL for haven-gitops repo
    chart_repo_url    — GitHub URL for Helm charts (InfraForge-Haven repo)
    target_revision   — e.g. "main"
    chart_path        — path to the haven-managed-service Helm chart

  Gitea repo structure: tenants/{tenant_slug}/services/{service_name}/values.yaml
  Path segments: [0]=tenants [1]=tenant_slug [2]=services [3]=service_name

  Naming convention:
    ApplicationSet name: svcset-{tenant_slug}
    Application name:    svc-{tenant_slug}-{service_name}
    Destination NS:      tenant-{tenant_slug}
#}
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: svcset-{{ tenant_slug }}
  namespace: argocd
  labels:
    haven.io/managed: "true"
    haven.io/tenant: "{{ tenant_slug }}"
    haven.io/type: "tenant-services"
spec:
  goTemplate: true
  goTemplateOptions: ["missingkey=error"]
  generators:
    - git:
        repoURL: {{ gitops_repo_url }}
        revision: {{ target_revision }}
        directories:
          - path: "tenants/{{ tenant_slug }}/services/*"
  template:
    metadata:
      # path.segments: [0]=tenants [1]=tenant_slug [2]=services [3]=service_name
      name: "svc-{{ tenant_slug }}-{% raw %}{{ index .path.segments 3 }}{% endraw %}"
      namespace: argocd
      labels:
        haven.io/managed: "true"
        haven.io/tenant: "{{ tenant_slug }}"
        haven.io/service: "{% raw %}{{ index .path.segments 3 }}{% endraw %}"
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
