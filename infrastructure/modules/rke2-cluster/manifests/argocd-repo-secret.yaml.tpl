---
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
  sshPrivateKey: |-
    ${indent(4, trimspace(github_ssh_deploy_key_private))}
