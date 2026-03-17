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
consoleIngress:
  enabled: true
  hosts:
    - ${minio_console_host}
  tls: []
ingress:
  enabled: true
  hosts:
    - ${minio_api_host}
  tls: []
tolerations:
  - operator: "Exists"
