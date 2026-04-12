# =============================================================================
#  iyziops — prod (platform, Helm chart versions, GitOps, OIDC)
# =============================================================================

# ----- Platform -------------------------------------------------------------

variable "platform_apex_domain" {
  description = "Apex domain for platform + tenant subdomains"
  type        = string
}

variable "gitops_repo_url" {
  description = "GitOps repo (git@github.com:... for private SSH)"
  type        = string
}

variable "gitops_target_revision" {
  description = "GitOps repo branch or tag"
  type        = string
  default     = "main"
}

# ----- Helm chart versions --------------------------------------------------

variable "longhorn_version" {
  description = "Longhorn chart version"
  type        = string
}

variable "longhorn_replica_count" {
  description = "Longhorn default replica count"
  type        = number
  default     = 3
}

variable "cert_manager_version" {
  description = "cert-manager chart version"
  type        = string
}

variable "argocd_version" {
  description = "ArgoCD chart version"
  type        = string
}

variable "argocd_server_replicas" {
  description = "ArgoCD server replica count"
  type        = number
}

variable "argocd_ha_enabled" {
  description = "Enable ArgoCD HA (Redis HA)"
  type        = bool
}

# ----- Keycloak OIDC --------------------------------------------------------

variable "keycloak_oidc_issuer_url" {
  description = "OIDC issuer URL for kube-apiserver"
  type        = string
}

variable "keycloak_oidc_client_id" {
  description = "OIDC client_id for kubectl"
  type        = string
}
