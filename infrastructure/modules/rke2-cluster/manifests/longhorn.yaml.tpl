---
apiVersion: v1
kind: Namespace
metadata:
  name: longhorn-system
  labels:
    pod-security.kubernetes.io/enforce: privileged
---
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: longhorn
  namespace: kube-system
spec:
  repo: https://charts.longhorn.io
  chart: longhorn
  version: "${longhorn_version}"
  targetNamespace: longhorn-system
  valuesContent: |-
    defaultSettings:
      defaultReplicaCount: ${longhorn_replica_count}
      defaultDataPath: /var/lib/longhorn/
      storageOverProvisioningPercentage: 100
      storageMinimalAvailablePercentage: 15
      backupTarget: ""
      backupTargetCredentialSecret: ""
      createDefaultDiskLabeledNodes: true
    persistence:
      defaultClass: true
      defaultClassReplicaCount: ${longhorn_replica_count}
      defaultDataLocality: best-effort
      reclaimPolicy: Delete
    longhornManager:
      tolerations:
        - operator: Exists
