---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: iyziops-root
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: iyziops-platform
  source:
    repoURL: "${gitops_repo_url}"
    targetRevision: "${gitops_target_revision}"
    path: platform/argocd/appsets
    directory:
      recurse: false
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ApplyOutOfSyncOnly=true
