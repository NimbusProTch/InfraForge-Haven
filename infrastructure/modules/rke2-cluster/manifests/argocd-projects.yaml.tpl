---
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: iyziops-platform
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  description: All platform services (operators, services, ingress, iyziops apps)
  sourceRepos:
    - "${gitops_repo_url}"
    - https://charts.longhorn.io
    - https://charts.jetstack.io
    - https://argoproj.github.io/argo-helm
    - https://charts.bitnami.com/bitnami
    - https://percona.github.io/percona-helm-charts
    - https://kyverno.github.io/kyverno
    - https://kyverno.github.io/kyverno/
    - https://prometheus-community.github.io/helm-charts
    - https://grafana.github.io/helm-charts
    - https://helm.goharbor.io
    - https://operator.min.io
    - https://dl.gitea.com/charts/
    - https://helm.releases.hashicorp.com
    - https://charts.external-secrets.io
    - https://charts.hetzner.cloud
    - https://github.com/kubernetes-sigs/gateway-api
  destinations:
    - server: https://kubernetes.default.svc
      namespace: "*"
  clusterResourceWhitelist:
    - group: "*"
      kind: "*"
  namespaceResourceWhitelist:
    - group: "*"
      kind: "*"
---
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: iyziops-tenants
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  description: Tenant workloads — restricted to tenant-* namespaces, no cluster-level resources
  sourceRepos:
    - "${gitops_repo_url}"
  destinations:
    - server: https://kubernetes.default.svc
      namespace: "tenant-*"
  clusterResourceWhitelist: []
  namespaceResourceWhitelist:
    - group: ""
      kind: "*"
    - group: apps
      kind: "*"
    - group: batch
      kind: "*"
    - group: networking.k8s.io
      kind: "*"
    - group: gateway.networking.k8s.io
      kind: "*"
    - group: autoscaling
      kind: "*"
