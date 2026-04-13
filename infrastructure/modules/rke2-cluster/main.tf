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
  #  Helm Controller manifests dropped at cluster bootstrap — MINIMAL SET.
  # ---------------------------------------------------------------------------
  #  Only the things the cluster cannot start without, plus the ArgoCD
  #  bootstrap. Everything else (Longhorn, cert-manager, ClusterIssuers,
  #  wildcard certificate, platform services, platform apps) is delivered
  #  by ArgoCD from the GitOps repo with proper sync-wave ordering.
  #
  #  In cloud-init at boot time:
  #    1. Cilium HelmChartConfig          — CNI tuning overlay
  #    2. Hetzner CCM HelmChart            — node init + LoadBalancer reconciler
  #                                          (must be present before nodes
  #                                          can leave the uninitialized
  #                                          taint set by --cloud-provider=external)
  #    3. cert-manager namespace            — pre-labelled for PSA restricted
  #    4. longhorn namespace                — pre-labelled privileged
  #    5. cloudflare API token Secret       — pre-created in cert-manager ns
  #    6. ArgoCD HelmChart                  — GitOps bootstrap
  #    7. ArgoCD AppProjects                 — platform + tenants projects
  #    8. ArgoCD repo Secret                 — SSH deploy key
  #    9. ArgoCD root Application            — points at platform/argocd/appsets/
  # ---------------------------------------------------------------------------

  manifest_cilium_config = templatefile("${path.module}/manifests/rke2-cilium-config.yaml.tpl", {
    cilium_operator_replicas = var.cilium_operator_replicas
    enable_hubble            = var.enable_hubble
  })

  manifest_hetzner_ccm = templatefile("${path.module}/manifests/hetzner-ccm.yaml.tpl", {
    hcloud_token        = var.hcloud_token
    network_name        = var.network_name
    ingress_lb_location = var.ingress_lb_location
    ccm_version         = var.hetzner_ccm_version
  })

  manifest_cert_manager_namespace = templatefile("${path.module}/manifests/cert-manager-namespace.yaml.tpl", {})

  manifest_longhorn_namespace = templatefile("${path.module}/manifests/longhorn-namespace.yaml.tpl", {})

  manifest_cloudflare_token_secret = templatefile("${path.module}/manifests/cloudflare-token-secret.yaml.tpl", {
    cloudflare_api_token = var.cloudflare_api_token
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
    gitops_repo_url = var.gitops_repo_url
  })

  manifest_argocd_root_app = templatefile("${path.module}/manifests/argocd-root-app.yaml.tpl", {
    gitops_repo_url        = var.gitops_repo_url
    gitops_target_revision = var.gitops_target_revision
  })

  # ---------------------------------------------------------------------------
  #  RKE2 config.yaml template — rendered twice (first master vs joining)
  # ---------------------------------------------------------------------------
  #  The RKE2 config body is rendered to its own file, base64-encoded, and
  #  dropped into cloud-init write_files with `encoding: b64`. Inline
  #  block scalars break with %{ if } directives because the directive line's
  #  leading whitespace concatenates with the next line's indent — base64
  #  is inert to cloud-init's YAML parser so directive strips work cleanly.

  rke2_config_vars_common = {
    cluster_token            = var.cluster_token
    first_master_private_ip  = var.first_master_private_ip
    lb_ip                    = var.lb_ip
    lb_private_ip            = var.lb_private_ip
    disable_kube_proxy       = var.disable_kube_proxy
    enable_cis_profile       = var.enable_cis_profile
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

  rke2_config_first_master = templatefile("${path.module}/templates/rke2-config.yaml.tpl", merge(local.rke2_config_vars_common, {
    is_first_master = true
  }))

  rke2_config_joining_master = templatefile("${path.module}/templates/rke2-config.yaml.tpl", merge(local.rke2_config_vars_common, {
    is_first_master = false
  }))

  rke2_config_worker = templatefile("${path.module}/templates/rke2-config-worker.yaml.tpl", {
    cluster_token           = var.cluster_token
    first_master_private_ip = var.first_master_private_ip
    enable_cis_profile      = var.enable_cis_profile
  })

  # ---------------------------------------------------------------------------
  #  Cloud-init strings
  # ---------------------------------------------------------------------------

  common_rke2_vars = {
    cluster_token           = var.cluster_token
    kubernetes_version      = var.kubernetes_version
    first_master_private_ip = var.first_master_private_ip
  }

  first_master_cloud_init = templatefile("${path.module}/templates/master-cloud-init.yaml.tpl", merge(local.common_rke2_vars, {
    rke2_config_b64                      = base64encode(local.rke2_config_first_master)
    manifest_cilium_config_b64           = base64encode(local.manifest_cilium_config)
    manifest_hetzner_ccm_b64             = base64encode(local.manifest_hetzner_ccm)
    manifest_cert_manager_namespace_b64  = base64encode(local.manifest_cert_manager_namespace)
    manifest_longhorn_namespace_b64      = base64encode(local.manifest_longhorn_namespace)
    manifest_cloudflare_token_secret_b64 = base64encode(local.manifest_cloudflare_token_secret)
    manifest_argocd_b64                  = base64encode(local.manifest_argocd)
    manifest_argocd_projects_b64         = base64encode(local.manifest_argocd_projects)
    manifest_argocd_repo_secret_b64      = base64encode(local.manifest_argocd_repo_secret)
    manifest_argocd_root_app_b64         = base64encode(local.manifest_argocd_root_app)
  }))

  joining_master_cloud_init = templatefile("${path.module}/templates/joining-master-cloud-init.yaml.tpl", merge(local.common_rke2_vars, {
    rke2_config_b64 = base64encode(local.rke2_config_joining_master)
  }))

  worker_cloud_init = templatefile("${path.module}/templates/worker-cloud-init.yaml.tpl", {
    kubernetes_version      = var.kubernetes_version
    first_master_private_ip = var.first_master_private_ip
    rke2_config_b64         = base64encode(local.rke2_config_worker)
  })
}
