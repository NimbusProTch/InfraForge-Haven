---
apiVersion: v1
kind: Namespace
metadata:
  name: cert-manager
---
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: cert-manager
  namespace: kube-system
spec:
  repo: https://charts.jetstack.io
  chart: cert-manager
  version: "${cert_manager_version}"
  targetNamespace: cert-manager
  valuesContent: |-
    installCRDs: true
    config:
      apiVersion: controller.config.cert-manager.io/v1alpha1
      kind: ControllerConfiguration
      enableGatewayAPI: true
    prometheus:
      enabled: false
    webhook:
      replicaCount: 2
    cainjector:
      replicaCount: 2
    replicaCount: 2
