# =============================================================================
#  iyziops — RKE2 cluster (core variables)
# =============================================================================
#  Cluster identity, networking, Cilium, hardening, OIDC. The variables for
#  etcd snapshots, Helm chart versions, ArgoCD, and GitOps live in their own
#  files to keep each variables file under the 200-line discipline cap.
# =============================================================================

# ----- Cluster identity ------------------------------------------------------

variable "cluster_name" {
  description = "Cluster name (used in resource labels and node naming)"
  type        = string
}

variable "kubernetes_version" {
  description = "RKE2 version tag (e.g. v1.32.3+rke2r1)"
  type        = string
}

variable "cluster_token" {
  description = "Shared secret used by joining masters and workers to register"
  type        = string
  sensitive   = true
}

# ----- Network ---------------------------------------------------------------

variable "first_master_private_ip" {
  description = "Private IP of the first master — used as server URL for joining nodes"
  type        = string
}

variable "lb_ip" {
  description = "Hetzner LB public IPv4 (tls-san and RKE2 fixed registration address)"
  type        = string
}

variable "lb_private_ip" {
  description = "Hetzner LB private IPv4 — Cilium k8sServiceHost"
  type        = string
}

# ----- Cilium ---------------------------------------------------------------

variable "enable_hubble" {
  description = "Enable Cilium Hubble observability (relay + UI)"
  type        = bool
  default     = true
}

variable "cilium_operator_replicas" {
  description = "Number of Cilium operator replicas"
  type        = number
  default     = 2
}

variable "disable_kube_proxy" {
  description = "Disable kube-proxy — Cilium eBPF replacement"
  type        = bool
  default     = true
}

# ----- Hardening ------------------------------------------------------------

variable "enable_cis_profile" {
  description = "Enable RKE2 CIS hardening profile"
  type        = bool
  default     = true
}

# ----- Keycloak OIDC --------------------------------------------------------

variable "keycloak_oidc_issuer_url" {
  description = "OIDC issuer URL for kube-apiserver token verification (no trailing slash)"
  type        = string
}

variable "keycloak_oidc_client_id" {
  description = "OIDC client_id used by kubectl"
  type        = string
}
