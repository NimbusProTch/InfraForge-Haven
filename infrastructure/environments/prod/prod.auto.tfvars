# =============================================================================
#  iyziops — prod environment (non-sensitive values, git-tracked)
# =============================================================================
#  Sensitive values (tokens, passwords, SSH deploy key) come from the
#  macOS Keychain via the `iyziops-env` shell function — they are never
#  committed. See .claude/rules/iac-discipline.md rule 9.
# =============================================================================

# ----- Identity -------------------------------------------------------------
cluster_name = "iyziops"
environment  = "prod"

# ----- Hetzner --------------------------------------------------------------
location_primary = "fsn1"
network_zone     = "eu-central"
network_cidr     = "10.10.0.0/16"
subnet_cidr      = "10.10.1.0/24"
lb_type          = "lb11"

# ⚠️  REPLACE before first apply — use your VPN / office egress CIDR.
operator_cidrs = ["203.0.113.0/24"]

# ----- Nodes ----------------------------------------------------------------
master_count       = 3
worker_count       = 3
master_server_type = "cpx32" # 4 vCPU / 8 GB
worker_server_type = "cpx42" # 8 vCPU / 16 GB
os_image           = "ubuntu-24.04"

# ----- RKE2 -----------------------------------------------------------------
kubernetes_version = "v1.32.3+rke2r1"
enable_cis_profile = true
enable_hubble      = true
disable_kube_proxy = true

# ----- etcd snapshot --------------------------------------------------------
#  Start local-only. Flip etcd_s3_enabled once the off-cluster bucket is
#  provisioned and credentials are in Keychain as TF_VAR_etcd_s3_*.
etcd_snapshot_schedule  = "0 2 * * *"
etcd_snapshot_retention = 30
etcd_s3_enabled         = false

# ----- Platform -------------------------------------------------------------
platform_apex_domain   = "iyziops.com"
gitops_repo_url        = "git@github.com:NimbusProTch/InfraForge-Haven.git"
gitops_target_revision = "main"

# ----- Helm chart versions --------------------------------------------------
longhorn_version       = "1.8.0"
longhorn_replica_count = 3
cert_manager_version   = "v1.17.0"
argocd_version         = "7.7.3"
argocd_server_replicas = 3
argocd_ha_enabled      = true

# ----- Keycloak OIDC (will be live once Keycloak is bootstrapped via GitOps) ---
keycloak_oidc_issuer_url = "https://keycloak.iyziops.com/realms/iyziops"
keycloak_oidc_client_id  = "iyziops-kubectl"

# Note: letsencrypt_email comes from iyziops-env (TF_VAR_letsencrypt_email)
# so it can be rotated without editing this file.
