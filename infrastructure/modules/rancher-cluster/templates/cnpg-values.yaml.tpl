# CloudNativePG Operator Helm values
# Operator only — Cluster CRD manifests are applied separately via ssh_resource
replicaCount: 1
resources:
  requests:
    cpu: "100m"
    memory: "256Mi"
  limits:
    memory: "512Mi"
tolerations:
  - operator: "Exists"
