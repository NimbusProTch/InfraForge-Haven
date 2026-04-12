---
apiVersion: v1
kind: Namespace
metadata:
  name: argocd
---
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: argocd
  namespace: kube-system
spec:
  repo: https://argoproj.github.io/argo-helm
  chart: argo-cd
  version: "${argocd_version}"
  targetNamespace: argocd
  valuesContent: |-
    global:
      domain: argocd.${platform_apex_domain}
    configs:
      secret:
        argocdServerAdminPassword: "${argocd_admin_password_bcrypt}"
      params:
        server.insecure: "true"
        application.namespaces: "argocd"
    server:
      replicas: ${argocd_server_replicas}
      service:
        type: ClusterIP
    controller:
      replicas: %{ if argocd_ha_enabled }2%{ else }1%{ endif }
    repoServer:
      replicas: ${argocd_server_replicas}
    applicationSet:
      replicas: 2
    redis-ha:
      enabled: ${argocd_ha_enabled}
    redis:
      enabled: %{ if argocd_ha_enabled }false%{ else }true%{ endif }
    dex:
      enabled: false
    notifications:
      enabled: false
