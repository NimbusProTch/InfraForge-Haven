# ============================================================
# Haven Platform - RKE2 Cluster Module
# ============================================================
# Creates an RKE2 cluster via Rancher with:
#   - Cilium CNI (built-in Helm controller, kube-proxy replacement)
#   - Configurable Hubble observability
#   - Rendered Longhorn values for storage installation
# ============================================================

# RKE2 Cluster with Cilium CNI (installed at bootstrap by RKE2 Helm controller)
resource "rancher2_cluster_v2" "cluster" {
  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version

  rke_config {
    chart_values = templatefile("${path.module}/templates/cilium-values.yaml.tpl", {
      operator_replicas = var.cilium_operator_replicas
      hubble_enabled    = var.enable_hubble
    })

    machine_global_config = yamlencode({
      cni                = "cilium"
      disable            = var.disabled_rke2_charts
      disable-kube-proxy = var.disable_kube_proxy
    })
  }
}
