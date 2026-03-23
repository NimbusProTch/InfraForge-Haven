# MinIO Helm values (S3-compatible Object Storage)
mode: standalone
replicas: 1
rootUser: ${minio_root_user}
rootPassword: ${minio_root_password}
persistence:
  enabled: true
  storageClass: longhorn
  size: ${minio_storage_size}
resources:
  requests:
    cpu: "100m"
    memory: "256Mi"
  limits:
    memory: "512Mi"
# Ingress disabled — Gateway API HTTPRoute handles external access
consoleIngress:
  enabled: false
ingress:
  enabled: false
tolerations:
  - operator: "Exists"
nodeSelector:
  node-role.kubernetes.io/worker: "true"
