---
# =============================================================================
#  Cilium HelmChartConfig — tuning overlay for RKE2's bundled Cilium chart
# =============================================================================
#  Routing mode: tunnel (VXLAN).
#
#  We originally tried native routing with autoDirectNodeRoutes + the
#  Hetzner subnet as ipv4NativeRoutingCIDR. Cilium rejected the direct
#  route install on every node with:
#
#    route to destination 10.10.1.X contains gateway 10.10.0.1,
#    must be directly reachable
#
#  Hetzner's private network advertises a /16 gateway (10.10.0.1), so
#  the Linux kernel refuses to install per-node pod-CIDR routes as
#  "direct". Cilium falls into degraded mode, pod-to-ClusterIP TCP
#  silently breaks, helm-install / cert-manager webhook / argocd repo
#  server all time out. Switching to VXLAN tunnel mode sidesteps the
#  direct-route requirement entirely: pod packets are encapsulated
#  and routed through the node's normal interface, no magic needed.
# =============================================================================
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: rke2-cilium
  namespace: kube-system
spec:
  valuesContent: |-
    kubeProxyReplacement: true
    k8sServiceHost: "${lb_private_ip}"
    k8sServicePort: 6443
    ipam:
      mode: kubernetes
    routingMode: tunnel
    tunnelProtocol: vxlan
    bpf:
      masquerade: true
    operator:
      replicas: ${cilium_operator_replicas}
    gatewayAPI:
      enabled: true
      enableAlpn: true
      enableAppProtocol: true
      # hostNetwork mode makes cilium-envoy bind the Gateway listeners
      # directly on host:80 and host:443 (no NodePort indirection, no
      # Hetzner CCM LoadBalancer reconciler). Requires the kernel sysctl
      # net.ipv4.ip_unprivileged_port_start=0 on every node because
      # cilium-envoy runs non-root — that sysctl is set in cloud-init
      # (/etc/sysctl.d/91-iyziops-gateway.conf) before rke2-server/agent
      # starts, so envoy can bind 80/443 on its first reconcile.
      hostNetwork:
        enabled: true
    envoy:
      enabled: true
    hubble:
      enabled: ${enable_hubble}
      relay:
        enabled: ${enable_hubble}
      ui:
        enabled: ${enable_hubble}
    encryption:
      enabled: true
      type: wireguard
      nodeEncryption: true
    tolerations:
      - operator: Exists
