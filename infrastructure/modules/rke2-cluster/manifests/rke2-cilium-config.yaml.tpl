---
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
    ipv4NativeRoutingCIDR: "${ipv4_native_routing_cidr}"
    routingMode: native
    autoDirectNodeRoutes: true
    bpf:
      masquerade: true
    operator:
      replicas: ${cilium_operator_replicas}
    gatewayAPI:
      enabled: true
      enableAlpn: true
      enableAppProtocol: true
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
