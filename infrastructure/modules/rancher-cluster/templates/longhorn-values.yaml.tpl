persistence:
  defaultClassReplicaCount: ${replica_count}
defaultSettings:
  defaultReplicaCount: ${replica_count}
  storageMinimalAvailablePercentage: 15
  defaultDataLocality: "best-effort"
  nodeDownPodDeletionPolicy: "delete-both-statefulset-and-deployment-pod"
longhornManager:
  tolerations:
    - operator: "Exists"
longhornDriver:
  tolerations:
    - operator: "Exists"
