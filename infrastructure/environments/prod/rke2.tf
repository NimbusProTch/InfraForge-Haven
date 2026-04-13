# =============================================================================
#  iyziops — prod RKE2 cluster wiring
# =============================================================================
#  rke2_cluster renders the three cloud-init strings consumed by hcloud_server
#  in hetzner.tf. rke2_install blocks tofu apply until the K8s API is
#  reachable via the LB.
# =============================================================================

module "rke2_cluster" {
  source = "../../modules/rke2-cluster"

  cluster_name            = var.cluster_name
  kubernetes_version      = var.kubernetes_version
  cluster_token           = random_password.cluster_token.result
  first_master_private_ip = local.first_master_private_ip
  lb_ip                   = module.hetzner_infra.load_balancer_ipv4
  lb_private_ip           = module.hetzner_infra.load_balancer_private_ipv4

  enable_cis_profile       = var.enable_cis_profile
  enable_hubble            = var.enable_hubble
  disable_kube_proxy       = var.disable_kube_proxy
  cilium_operator_replicas = 2

  keycloak_oidc_issuer_url = var.keycloak_oidc_issuer_url
  keycloak_oidc_client_id  = var.keycloak_oidc_client_id

  etcd_snapshot_schedule  = var.etcd_snapshot_schedule
  etcd_snapshot_retention = var.etcd_snapshot_retention
  etcd_s3_enabled         = var.etcd_s3_enabled
  etcd_s3_endpoint        = var.etcd_s3_endpoint
  etcd_s3_bucket          = var.etcd_s3_bucket
  etcd_s3_region          = var.etcd_s3_region
  etcd_s3_access_key      = var.etcd_s3_access_key
  etcd_s3_secret_key      = var.etcd_s3_secret_key

  platform_apex_domain = var.platform_apex_domain
  letsencrypt_email    = var.letsencrypt_email
  cloudflare_api_token = var.cloudflare_api_token

  argocd_version               = var.argocd_version
  argocd_server_replicas       = var.argocd_server_replicas
  argocd_ha_enabled            = var.argocd_ha_enabled
  argocd_admin_password_bcrypt = var.argocd_admin_password_bcrypt

  gitops_repo_url               = var.gitops_repo_url
  gitops_target_revision        = var.gitops_target_revision
  github_ssh_deploy_key_private = var.github_ssh_deploy_key_private
}

module "rke2_install" {
  source = "../../modules/rke2-install"

  lb_ip = module.hetzner_infra.load_balancer_ipv4

  depends_on = [
    hcloud_load_balancer_target.master,
    hcloud_load_balancer_target.worker,
  ]
}
