# =============================================================================
#  iyziops — RKE2 cluster (main)
# =============================================================================
#  This module produces THREE cloud-init strings:
#
#    1. first_master_cloud_init    — bootstrap master with cluster-init=true
#                                    and every Helm Controller manifest
#                                    dropped into /var/lib/rancher/rke2/
#                                    server/manifests/. Helm Controller
#                                    applies them when rke2-server starts.
#
#    2. joining_master_cloud_init  — other masters, join via private IP:9345,
#                                    no manifests (etcd replicates them).
#
#    3. worker_cloud_init          — agents joining via private IP:9345.
#
#  All manifest bodies are rendered from the manifests/ directory
#  as locals below, then base64-encoded and dropped into the master's
#  cloud-init write_files block. Base64 keeps indentation and special
#  characters from breaking the outer YAML.
# =============================================================================

locals {
  # ---------------------------------------------------------------------------
  #  Helm Controller manifests — rendered from sub-templates, base64-encoded
  #  so they can be embedded cleanly into the cloud-init write_files block.
  # ---------------------------------------------------------------------------

  manifest_cilium_config = templatefile("${path.module}/manifests/rke2-cilium-config.yaml.tpl", {
    cilium_operator_replicas = var.cilium_operator_replicas
    enable_hubble            = var.enable_hubble
    ipv4_native_routing_cidr = var.ipv4_native_routing_cidr
    lb_private_ip            = var.lb_private_ip
  })

  manifest_longhorn = templatefile("${path.module}/manifests/longhorn.yaml.tpl", {
    longhorn_version       = var.longhorn_version
    longhorn_replica_count = var.longhorn_replica_count
  })

  manifest_cert_manager = templatefile("${path.module}/manifests/cert-manager.yaml.tpl", {
    cert_manager_version = var.cert_manager_version
  })

  manifest_cloudflare_token_secret = templatefile("${path.module}/manifests/cloudflare-token-secret.yaml.tpl", {
    cloudflare_api_token = var.cloudflare_api_token
  })

  manifest_letsencrypt_issuers = templatefile("${path.module}/manifests/letsencrypt-issuers.yaml.tpl", {
    letsencrypt_email = var.letsencrypt_email
  })

  manifest_wildcard_cert = templatefile("${path.module}/manifests/iyziops-wildcard-cert.yaml.tpl", {
    platform_apex_domain = var.platform_apex_domain
  })

  manifest_argocd = templatefile("${path.module}/manifests/argocd.yaml.tpl", {
    argocd_version               = var.argocd_version
    argocd_server_replicas       = var.argocd_server_replicas
    argocd_ha_enabled            = var.argocd_ha_enabled
    argocd_admin_password_bcrypt = var.argocd_admin_password_bcrypt
    platform_apex_domain         = var.platform_apex_domain
  })

  manifest_argocd_projects = templatefile("${path.module}/manifests/argocd-projects.yaml.tpl", {
    gitops_repo_url = var.gitops_repo_url
  })

  manifest_argocd_repo_secret = templatefile("${path.module}/manifests/argocd-repo-secret.yaml.tpl", {
    gitops_repo_url               = var.gitops_repo_url
    github_ssh_deploy_key_private = var.github_ssh_deploy_key_private
  })

  manifest_argocd_root_app = templatefile("${path.module}/manifests/argocd-root-app.yaml.tpl", {
    gitops_repo_url        = var.gitops_repo_url
    gitops_target_revision = var.gitops_target_revision
  })

  # ---------------------------------------------------------------------------
  #  Master cloud-init receives every manifest + the cluster config.
  #  The template encodes each manifest in base64 so write_files can drop
  #  them at /var/lib/rancher/rke2/server/manifests/*.yaml verbatim.
  # ---------------------------------------------------------------------------

  common_rke2_vars = {
    cluster_token            = var.cluster_token
    kubernetes_version       = var.kubernetes_version
    first_master_private_ip  = var.first_master_private_ip
    lb_ip                    = var.lb_ip
    lb_private_ip            = var.lb_private_ip
    enable_cis_profile       = var.enable_cis_profile
    disable_kube_proxy       = var.disable_kube_proxy
    keycloak_oidc_issuer_url = var.keycloak_oidc_issuer_url
    keycloak_oidc_client_id  = var.keycloak_oidc_client_id
    etcd_snapshot_schedule   = var.etcd_snapshot_schedule
    etcd_snapshot_retention  = var.etcd_snapshot_retention
    etcd_s3_enabled          = var.etcd_s3_enabled
    etcd_s3_endpoint         = var.etcd_s3_endpoint
    etcd_s3_bucket           = var.etcd_s3_bucket
    etcd_s3_region           = var.etcd_s3_region
    etcd_s3_access_key       = var.etcd_s3_access_key
    etcd_s3_secret_key       = var.etcd_s3_secret_key
  }

  first_master_cloud_init = templatefile("${path.module}/templates/master-cloud-init.yaml.tpl", merge(local.common_rke2_vars, {
    manifest_cilium_config_b64           = base64encode(local.manifest_cilium_config)
    manifest_longhorn_b64                = base64encode(local.manifest_longhorn)
    manifest_cert_manager_b64            = base64encode(local.manifest_cert_manager)
    manifest_cloudflare_token_secret_b64 = base64encode(local.manifest_cloudflare_token_secret)
    manifest_letsencrypt_issuers_b64     = base64encode(local.manifest_letsencrypt_issuers)
    manifest_wildcard_cert_b64           = base64encode(local.manifest_wildcard_cert)
    manifest_argocd_b64                  = base64encode(local.manifest_argocd)
    manifest_argocd_projects_b64         = base64encode(local.manifest_argocd_projects)
    manifest_argocd_repo_secret_b64      = base64encode(local.manifest_argocd_repo_secret)
    manifest_argocd_root_app_b64         = base64encode(local.manifest_argocd_root_app)
  }))

  joining_master_cloud_init = templatefile("${path.module}/templates/joining-master-cloud-init.yaml.tpl", local.common_rke2_vars)

  worker_cloud_init = templatefile("${path.module}/templates/worker-cloud-init.yaml.tpl", {
    cluster_token           = var.cluster_token
    kubernetes_version      = var.kubernetes_version
    first_master_private_ip = var.first_master_private_ip
    enable_cis_profile      = var.enable_cis_profile
  })
}
