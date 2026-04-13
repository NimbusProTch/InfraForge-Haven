---
# =============================================================================
#  Hetzner Cloud Controller Manager — bootstrap HelmChart
# =============================================================================
#  Installs hcloud-cloud-controller-manager from the official Hetzner Helm
#  repo via RKE2's in-cluster Helm Controller. Drops at first-master boot
#  alongside the Cilium HelmChartConfig. Order is irrelevant: both manifests
#  reach Helm Controller, which applies them as soon as the apiserver is up.
#
#  The CCM does three things we need:
#    1. Initializes nodes (writes spec.providerID = "hcloud://<server-id>"
#       and topology.kubernetes.io/{zone,region} labels), then removes the
#       node.cloudprovider.kubernetes.io/uninitialized taint set by kubelet
#       when --cloud-provider=external is passed. Without this every node
#       sits NotReady forever.
#    2. Reconciles LoadBalancer Services declaratively. When a Service
#       carries the load-balancer.hetzner.cloud/name annotation, CCM finds
#       the existing Hetzner LB by that literal name and adopts it (writes
#       the hcloud-ccm/service-uid label, then keeps services + targets
#       in sync). The Cilium Gateway → cilium-gateway-iyziops-gateway
#       Service propagates spec.infrastructure.annotations from our
#       iyziops-gateway Gateway resource, which carries the name annotation.
#    3. Optional route controller (left disabled — we use Cilium VXLAN
#       tunnel mode, no native routing).
#
#  hostNetwork is required (default in upstream chart) because the CCM
#  needs to run before any pod networking is up — it has to initialize
#  the very nodes that Cilium pods would otherwise schedule onto.
#
#  Tolerations include the uninitialized taint so CCM can land on a
#  freshly-booted node and unstick the cluster, and CriticalAddonsOnly
#  so it tolerates the master taint and runs on control-plane nodes.
# =============================================================================
apiVersion: v1
kind: Secret
metadata:
  name: hcloud
  namespace: kube-system
type: Opaque
stringData:
  token: "${hcloud_token}"
  network: "${network_name}"
---
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: hcloud-cloud-controller-manager
  namespace: kube-system
spec:
  repo: https://charts.hetzner.cloud
  chart: hcloud-cloud-controller-manager
  targetNamespace: kube-system
  version: "${ccm_chart_version}"
  valuesContent: |-
    networking:
      enabled: true
      clusterCIDR: "10.42.0.0/16"
    env:
      HCLOUD_LOAD_BALANCERS_ENABLED:
        value: "true"
      HCLOUD_LOAD_BALANCERS_LOCATION:
        value: "${ingress_lb_location}"
      HCLOUD_LOAD_BALANCERS_USE_PRIVATE_IP:
        value: "true"
      HCLOUD_LOAD_BALANCERS_DISABLE_PRIVATE_INGRESS:
        value: "true"
      HCLOUD_NETWORK:
        valueFrom:
          secretKeyRef:
            name: hcloud
            key: network
      HCLOUD_TOKEN:
        valueFrom:
          secretKeyRef:
            name: hcloud
            key: token
    nodeSelector:
      node-role.kubernetes.io/control-plane: "true"
    tolerations:
      - key: "node.cloudprovider.kubernetes.io/uninitialized"
        value: "true"
        effect: "NoSchedule"
      - key: "node.kubernetes.io/not-ready"
        effect: "NoSchedule"
      - key: "node-role.kubernetes.io/control-plane"
        effect: "NoSchedule"
      - key: "node-role.kubernetes.io/master"
        effect: "NoSchedule"
      - key: "CriticalAddonsOnly"
        operator: "Exists"
        effect: "NoExecute"
