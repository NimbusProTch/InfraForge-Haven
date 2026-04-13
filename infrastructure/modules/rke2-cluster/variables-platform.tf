# =============================================================================
#  iyziops — RKE2 cluster (platform service variables)
# =============================================================================
#  Helm chart versions + platform apex domain + Cloudflare token + ArgoCD
#  configuration + GitOps repo credentials.
# =============================================================================

# ----- Platform domain & Cloudflare -----------------------------------------

variable "platform_apex_domain" {
  description = "Platform apex domain (e.g. iyziops.com) — used for wildcard cert and ingress"
  type        = string
}

variable "letsencrypt_email" {
  description = "Email address used for Let's Encrypt account registration"
  type        = string
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token for cert-manager DNS-01 solver"
  type        = string
  sensitive   = true
}

# ----- Helm chart versions --------------------------------------------------
#  cert-manager, Longhorn, and every other platform service are now
#  installed by ArgoCD (see platform/argocd/apps/services/). Only the
#  ArgoCD chart itself is still installed at bootstrap via Helm Controller.

variable "argocd_version" {
  description = "ArgoCD Helm chart version"
  type        = string
}

variable "argocd_server_replicas" {
  description = "Number of argocd-server replicas"
  type        = number
  default     = 3
}

variable "argocd_ha_enabled" {
  description = "Enable ArgoCD HA mode (Redis HA, multiple controllers)"
  type        = bool
  default     = true
}

variable "argocd_admin_password_bcrypt" {
  description = "bcrypt hash of the ArgoCD admin password"
  type        = string
  sensitive   = true
}

# ----- GitOps repo ----------------------------------------------------------

variable "gitops_repo_url" {
  description = "GitOps repository URL (git@ or https:// form)"
  type        = string
}

variable "gitops_target_revision" {
  description = "GitOps repository branch / tag"
  type        = string
  default     = "main"
}

variable "github_ssh_deploy_key_private" {
  description = "Private SSH deploy key for the GitOps repo (read-only)"
  type        = string
  sensitive   = true
}
