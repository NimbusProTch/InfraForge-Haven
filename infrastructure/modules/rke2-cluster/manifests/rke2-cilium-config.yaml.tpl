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
#  "direct". Switching to VXLAN tunnel mode sidesteps the requirement
#  entirely. (Native routing would also need Hetzner CCM's route-controller
#  to write per-node routes into the private network — kube-hetzner default
#  is also tunnel mode for this same reason.)
#
#  k8sServiceHost = 127.0.0.1 — every RKE2 node (server + agent) exposes
#  the Kubernetes API on the loopback at port 6443 (servers run apiserver
#  directly; agents run a local agent-lb). Pointing Cilium at the loopback
#  removes any dependency on the Hetzner LB during early bootstrap, breaking
#  the chicken-and-egg between CNI install and the API LB DNS resolution.
#  This is the same pattern kube-hetzner uses (k8sServiceHost = 127.0.0.1
#  on k3s 6444) and hcloud-k8s uses (KubePrism on 7445 for Talos).
#
#  Gateway API: enabled in standard mode — Cilium creates a LoadBalancer
#  Service per Gateway. The Hetzner CCM (installed via hetzner-ccm.yaml)
#  adopts the corresponding Hetzner LB by name and writes the 80/443
#  services. No more hostNetwork mode, no more sysctl unprivileged port
#  workaround — this is the upstream-recommended pathway.
# =============================================================================
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: rke2-cilium
  namespace: kube-system
spec:
  valuesContent: |-
    kubeProxyReplacement: true
    k8sServiceHost: "127.0.0.1"
    k8sServicePort: 6443
    # Cilium helm key is capital "MTU" — lowercase "mtu" is silently
    # ignored (Cilium then autodetects from the primary NIC and can pick
    # a wrong value, causing non-deterministic packet drops on the
    # cross-DC fsn1↔nbg1 vxlan path). 1450 matches Hetzner's private
    # network underlay; Cilium subtracts its own vxlan overhead to set
    # the pod interface MTU internally. Source: kube-hetzner locals.tf.
    MTU: 1450
    ipam:
      mode: kubernetes
    routingMode: tunnel
    tunnelProtocol: vxlan
    bpf:
      masquerade: true
    cni:
      exclusive: true
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
