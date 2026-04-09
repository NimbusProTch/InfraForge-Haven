# ============================================================
# RKE2 Cluster Module
# ============================================================
# Direct RKE2 installation without Rancher.
# Generates cloud-init configs for master and worker nodes.
# Cilium CNI configured via RKE2 HelmChartConfig.
# ============================================================

locals {
  # H1b-2 (P4.2): etcd snapshot template variables — passed to both
  # first-master and joining-master cloud-init renders so all 3 masters
  # carry the same snapshot config. The S3 fields are interpolated into
  # the template's `%{ if etcd_s3_enabled }` block — when disabled they
  # are still defined (template needs the keys to exist) but unused.
  _etcd_template_vars = {
    etcd_snapshot_schedule  = var.etcd_snapshot_schedule
    etcd_snapshot_retention = var.etcd_snapshot_retention
    etcd_s3_enabled         = var.etcd_s3_enabled
    etcd_s3_endpoint        = var.etcd_s3_endpoint
    etcd_s3_bucket          = var.etcd_s3_bucket
    etcd_s3_folder          = var.etcd_s3_folder
    etcd_s3_region          = var.etcd_s3_region
    etcd_s3_access_key      = var.etcd_s3_access_key
    etcd_s3_secret_key      = var.etcd_s3_secret_key
  }

  # H1a-2: kubectl OIDC integration. The master cloud-init writes
  # `--oidc-issuer-url` and `--oidc-client-id` flags to the kube-apiserver
  # config. Defaults point at the dev cluster Keycloak. Operator must
  # ensure the Keycloak realm has the `groups` protocolMapper enabled
  # (see keycloak/haven-realm.json) and a `haven-kubectl` public client
  # exists for tenant admins to obtain tokens.
  _oidc_template_vars = {
    keycloak_oidc_issuer_url = var.keycloak_oidc_issuer_url
    keycloak_oidc_client_id  = var.keycloak_oidc_client_id
  }

  master_cloud_init = templatefile("${path.module}/templates/master-cloud-init.yaml.tpl", merge({
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
  }, local._etcd_template_vars, local._oidc_template_vars))

  joining_master_cloud_init = templatefile("${path.module}/templates/master-cloud-init.yaml.tpl", merge({
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
  }, local._etcd_template_vars, local._oidc_template_vars))

  worker_cloud_init = templatefile("${path.module}/templates/worker-cloud-init.yaml.tpl", {
    cluster_token           = var.cluster_token
    first_master_private_ip = var.first_master_private_ip
    kubernetes_version      = var.kubernetes_version
    enable_cis_profile      = var.enable_cis_profile
  })
}
