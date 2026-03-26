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
