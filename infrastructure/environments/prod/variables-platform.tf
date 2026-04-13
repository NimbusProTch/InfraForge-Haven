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
#  Longhorn + cert-manager versions now live in the ArgoCD Application
#  manifests (platform/argocd/apps/services/) because those components
#  are installed by ArgoCD after the cluster is ready, not at bootstrap.

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
