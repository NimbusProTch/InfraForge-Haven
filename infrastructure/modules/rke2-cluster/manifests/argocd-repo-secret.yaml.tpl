---
# =============================================================================
#  ArgoCD repo secret — public HTTPS GitOps repo
# =============================================================================
#  The InfraForge-Haven repo is public, so ArgoCD does not need any
#  credentials to clone it. We only register the repo so it appears in the
#  ArgoCD UI as a known source.
#
#  We deliberately do NOT set sshPrivateKey here. ArgoCD interprets any
#  non-empty sshPrivateKey as "use SSH auth" and tries to dial git@github.com,
#  which fails with "ssh: no key found" because the URL is https://. If the
#  repo is ever flipped back to private, switch the url to git@github.com:...
#  and add sshPrivateKey from a Keychain-backed Secret reference.
# =============================================================================
apiVersion: v1
kind: Secret
metadata:
  name: iyziops-platform-repo
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repository
type: Opaque
stringData:
  type: git
  url: "${gitops_repo_url}"
