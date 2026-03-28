# LimitRange — per-tenant container + PVC size limits
# Template variables: NAMESPACE, PVC_MAX
#
# Container limits are fixed across all tiers:
#   default limit:   cpu=500m,  memory=512Mi
#   default request: cpu=100m,  memory=128Mi
#   min:             cpu=10m,   memory=32Mi
#   max:             cpu=4,     memory=4Gi
#
# PVC max varies by tier (tenant_service.py _TIER_PVC_MAX):
#   free/dev/starter:   PVC_MAX=50Gi
#   standard/pro:       PVC_MAX=200Gi
#   premium/enterprise: PVC_MAX=1Ti
#
# Applied automatically by Haven API on tenant creation.
---
apiVersion: v1
kind: LimitRange
metadata:
  name: tenant-limits
  namespace: ${NAMESPACE}
spec:
  limits:
    - type: Container
      default:
        cpu: "500m"
        memory: "512Mi"
      defaultRequest:
        cpu: "100m"
        memory: "128Mi"
      min:
        cpu: "10m"
        memory: "32Mi"
      max:
        cpu: "4"
        memory: "4Gi"
    - type: PersistentVolumeClaim
      min:
        storage: "1Gi"
      max:
        storage: "${PVC_MAX}"
