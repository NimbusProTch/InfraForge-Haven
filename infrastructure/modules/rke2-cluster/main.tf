# ============================================================
# RKE2 Cluster Module
# ============================================================
# Direct RKE2 installation without Rancher.
# Generates cloud-init configs for master and worker nodes.
# Cilium CNI configured via RKE2 HelmChartConfig.
# ============================================================

locals {
  master_cloud_init = templatefile("${path.module}/templates/master-cloud-init.yaml.tpl", {
    cluster_token            = var.cluster_token
    first_master_private_ip  = var.first_master_private_ip
    is_first_master          = true
    lb_ip                    = var.lb_ip
    lb_private_ip            = var.lb_private_ip
    kubernetes_version       = var.kubernetes_version
    enable_hubble            = var.enable_hubble
    cilium_operator_replicas = var.cilium_operator_replicas
    disable_kube_proxy       = var.disable_kube_proxy
    enable_cis_profile       = var.enable_cis_profile
  })

  joining_master_cloud_init = templatefile("${path.module}/templates/master-cloud-init.yaml.tpl", {
    cluster_token            = var.cluster_token
    first_master_private_ip  = var.first_master_private_ip
    is_first_master          = false
    lb_ip                    = var.lb_ip
    lb_private_ip            = var.lb_private_ip
    kubernetes_version       = var.kubernetes_version
    enable_hubble            = var.enable_hubble
    cilium_operator_replicas = var.cilium_operator_replicas
    disable_kube_proxy       = var.disable_kube_proxy
    enable_cis_profile       = var.enable_cis_profile
  })

  worker_cloud_init = templatefile("${path.module}/templates/worker-cloud-init.yaml.tpl", {
    cluster_token           = var.cluster_token
    first_master_private_ip = var.first_master_private_ip
    kubernetes_version      = var.kubernetes_version
    enable_cis_profile      = var.enable_cis_profile
  })
}
