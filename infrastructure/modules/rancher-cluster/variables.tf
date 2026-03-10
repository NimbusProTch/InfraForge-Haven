# ===== Cluster =====
variable "cluster_name" {
  description = "RKE2 cluster name"
  type        = string
}

variable "kubernetes_version" {
  description = "RKE2 Kubernetes version"
  type        = string
}

# ===== Cilium CNI =====
variable "enable_hubble" {
  description = "Enable Hubble observability (UI + Relay)"
  type        = bool
  default     = true
}

variable "cilium_operator_replicas" {
  description = "Number of Cilium operator replicas"
  type        = number
  default     = 1
}

variable "disable_kube_proxy" {
  description = "Let Cilium replace kube-proxy (eBPF)"
  type        = bool
  default     = true
}

variable "disabled_rke2_charts" {
  description = "RKE2 built-in Helm charts to disable"
  type        = list(string)
  default     = ["rke2-ingress-nginx"]
}

# ===== Longhorn Storage =====
variable "longhorn_replica_count" {
  description = "Longhorn default replica count (auto-set from worker_count)"
  type        = number
  default     = 1
}
