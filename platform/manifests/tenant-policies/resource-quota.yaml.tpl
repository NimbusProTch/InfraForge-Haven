# ResourceQuota — per-tenant resource limits
# Template variables: NAMESPACE, CPU_LIMIT, MEMORY_LIMIT, STORAGE_LIMIT,
#                     PODS, PVCS, SERVICES
#
# Tier defaults applied by Haven API (tenant_service.py _TIER_QUOTAS):
#   free/dev/starter:  pods=10-20, pvcs=3-5,   services=5-10
#   standard/pro:      pods=50,    pvcs=20,     services=20
#   premium/enterprise:pods=200,   pvcs=100,    services=50
#
# CPU/Memory/Storage come from Tenant.{cpu,memory,storage}_limit DB fields.
# Applied automatically by Haven API on tenant creation.
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: tenant-quota
  namespace: ${NAMESPACE}
spec:
  hard:
    requests.cpu: "${CPU_LIMIT}"
    limits.cpu: "${CPU_LIMIT}"
    requests.memory: "${MEMORY_LIMIT}"
    limits.memory: "${MEMORY_LIMIT}"
    requests.storage: "${STORAGE_LIMIT}"
    pods: "${PODS}"
    persistentvolumeclaims: "${PVCS}"
    services: "${SERVICES}"
