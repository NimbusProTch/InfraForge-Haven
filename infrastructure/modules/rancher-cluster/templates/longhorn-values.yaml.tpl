persistence:
  defaultClassReplicaCount: ${replica_count}
defaultSettings:
  defaultReplicaCount: ${replica_count}
  storageMinimalAvailablePercentage: 15
  defaultDataLocality: "best-effort"
  nodeDownPodDeletionPolicy: "delete-both-statefulset-and-deployment-pod"
  # Allow Longhorn uninstall to proceed even with existing volumes
  # Without this, uninstall hangs waiting for manual confirmation
  deletingConfirmationFlag: true
longhornManager:
  tolerations:
    - operator: "Exists"
longhornDriver:
  tolerations:
    - operator: "Exists"
