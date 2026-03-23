# Harbor Helm values (Image Registry)
# Self-hosted, Trivy vulnerability scanning enabled
expose:
  # Use clusterIP — Gateway API HTTPRoute handles external access
  type: clusterIP
  tls:
    enabled: false
externalURL: http://${harbor_host}
harborAdminPassword: ${harbor_admin_password}
persistence:
  enabled: true
  persistentVolumeClaim:
    registry:
      storageClass: longhorn
      size: ${registry_storage_size}
    database:
      storageClass: longhorn
      size: 2Gi
    redis:
      storageClass: longhorn
      size: 1Gi
    jobservice:
      jobLog:
        storageClass: longhorn
        size: 1Gi
    trivy:
      storageClass: longhorn
      size: 5Gi
database:
  type: internal
redis:
  type: internal
trivy:
  enabled: true
tolerations:
  - operator: "Exists"
