# ArgoCD Helm values (dev: single replica, TLS terminated at Gateway)
global:
  tolerations:
    - operator: "Exists"
configs:
  params:
    server.insecure: "true"
server:
  replicas: 1
  ingress:
    enabled: false
  ingressGrpc:
    enabled: false
applicationSet:
  replicas: 1
controller:
  replicas: 1
redis:
  enabled: true
redis-ha:
  enabled: false
dex:
  enabled: false
