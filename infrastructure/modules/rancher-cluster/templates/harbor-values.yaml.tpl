# Harbor Helm values (Image Registry)
# Self-hosted, Trivy vulnerability scanning enabled
expose:
  type: ingress
  tls:
    enabled: true
    certSource: secret
    secret:
      secretName: harbor-tls
  ingress:
    hosts:
      core: ${harbor_host}
    className: ""
    annotations:
      cert-manager.io/cluster-issuer: ""
externalURL: https://${harbor_host}
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
