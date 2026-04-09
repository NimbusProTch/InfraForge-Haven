# ============================================================
# RKE2 Cluster Module - Variables
# ============================================================
# Direct RKE2 installation (no Rancher dependency)
# ============================================================

variable "cluster_name" {
  description = "Cluster name (used for node naming and labels)"
  type        = string
}

variable "kubernetes_version" {
  description = "RKE2 Kubernetes version"
  type        = string
  default     = "v1.32.3+rke2r1"
}

variable "cluster_token" {
  description = "Shared secret for node registration"
  type        = string
  sensitive   = true
}

# ===== Network =====
variable "first_master_private_ip" {
  description = "Private IP of the first master (for joining other nodes)"
  type        = string
}

variable "lb_ip" {
  description = "Load balancer public IP (for TLS SAN)"
  type        = string
}

variable "lb_private_ip" {
  description = "Load balancer private IP (optional)"
  type        = string
  default     = ""
}

# ===== Cilium CNI =====
variable "enable_hubble" {
  description = "Enable Hubble observability (Cilium)"
  type        = bool
  default     = true
}

variable "cilium_operator_replicas" {
  description = "Number of Cilium operator replicas"
  type        = number
  default     = 1
}

variable "disable_kube_proxy" {
  description = "Disable kube-proxy (Cilium eBPF replacement)"
  type        = bool
  default     = true
}

# ===== CIS Hardening =====
variable "enable_cis_profile" {
  description = "Enable RKE2 CIS hardening profile"
  type        = bool
  default     = true
}

# ===== H1b-2 (P4.2): etcd snapshot schedule + off-cluster S3 upload =====
# Pre-fix the cluster had ZERO automated etcd snapshots — total cluster
# loss = total data loss (every tenant + Harbor + Gitea + Keycloak).
# These variables wire RKE2's native `etcd-snapshot-*` flags via the
# master cloud-init template.

variable "etcd_snapshot_schedule" {
  description = "Cron expression for automated etcd snapshots. Default: daily 02:00 UTC."
  type        = string
  default     = "0 2 * * *"
}

variable "etcd_snapshot_retention" {
  description = "Number of local etcd snapshots to retain on each master before pruning"
  type        = number
  default     = 30
}

variable "etcd_s3_enabled" {
  description = "Ship etcd snapshots to off-cluster S3-compatible bucket. MUST be true for real DR."
  type        = bool
  default     = false
}

variable "etcd_s3_endpoint" {
  description = "S3-compatible endpoint URL (e.g. <account>.r2.cloudflarestorage.com for Cloudflare R2)"
  type        = string
  default     = ""
}

variable "etcd_s3_bucket" {
  description = "S3 bucket name for etcd snapshots"
  type        = string
  default     = ""
}

variable "etcd_s3_folder" {
  description = "Subfolder inside the bucket (e.g. \"dev\" / \"production\")"
  type        = string
  default     = ""
}

variable "etcd_s3_region" {
  description = "S3 region (use \"auto\" for Cloudflare R2)"
  type        = string
  default     = "auto"
}

variable "etcd_s3_access_key" {
  description = "S3 access key — set via TF_VAR_etcd_s3_access_key or terraform.tfvars"
  type        = string
  default     = ""
  sensitive   = true
}

variable "etcd_s3_secret_key" {
  description = "S3 secret key — set via TF_VAR_etcd_s3_secret_key or terraform.tfvars"
  type        = string
  default     = ""
  sensitive   = true
}

# ===== H1a-2: kubectl OIDC integration via Keycloak =====
# Pre-fix the dev cluster had ZERO --oidc-* flags on kube-apiserver, so
# tenant admins could not use their Keycloak token with `kubectl`. The
# defaults below match the dev cluster's haven realm at the sslip.io
# Keycloak instance. Override in the env tfvars for production.

variable "keycloak_oidc_issuer_url" {
  description = "OIDC issuer URL for kube-apiserver token verification. Must match the `iss` claim in Keycloak-issued JWTs (no trailing slash)."
  type        = string
  default     = "https://keycloak.46.225.42.2.sslip.io/realms/haven"
}

variable "keycloak_oidc_client_id" {
  description = "OIDC client_id used by kubectl to obtain tokens from Keycloak. Must exist in the haven realm as a public client (see keycloak/haven-realm.json)."
  type        = string
  default     = "haven-kubectl"
}
