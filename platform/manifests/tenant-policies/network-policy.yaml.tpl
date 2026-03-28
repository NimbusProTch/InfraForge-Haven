# CiliumNetworkPolicy — per-tenant L7 network isolation
# Template variables: NAMESPACE (e.g. tenant-acme)
#
# Ingress allowed:
#   - Same namespace (intra-tenant pod communication)
#   - haven-system (Haven API deployment/health checks)
#   - monitoring (Prometheus scraping /metrics)
#
# Egress allowed:
#   - Same namespace (intra-tenant pod communication)
#   - kube-system:53 (kube-dns name resolution)
#   - world entity (internet — external APIs, registries, etc.)
#
# Everything else is denied by default.
# Applied automatically by Haven API on tenant creation.
---
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: tenant-isolation
  namespace: ${NAMESPACE}
spec:
  endpointSelector: {}
  ingress:
    - fromEndpoints:
        - matchLabels:
            io.kubernetes.pod.namespace: ${NAMESPACE}
    - fromEndpoints:
        - matchLabels:
            io.kubernetes.pod.namespace: haven-system
    - fromEndpoints:
        - matchLabels:
            io.kubernetes.pod.namespace: monitoring
  egress:
    - toEndpoints:
        - matchLabels:
            io.kubernetes.pod.namespace: ${NAMESPACE}
    - toEndpoints:
        - matchLabels:
            io.kubernetes.pod.namespace: kube-system
      toPorts:
        - ports:
            - port: "53"
              protocol: UDP
            - port: "53"
              protocol: TCP
    - toEntities:
        - world
