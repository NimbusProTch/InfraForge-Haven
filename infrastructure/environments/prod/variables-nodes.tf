# =============================================================================
#  iyziops — prod (node sizing + RKE2 cluster config)
# =============================================================================

# ----- Nodes ----------------------------------------------------------------

variable "master_count" {
  description = "Number of control-plane nodes"
  type        = number

  validation {
    condition     = var.master_count >= 3 && var.master_count % 2 == 1
    error_message = "master_count must be odd and at least 3 (etcd quorum)."
  }
}

variable "worker_count" {
  description = "Number of agent nodes"
  type        = number

  validation {
    condition     = var.worker_count >= 3
    error_message = "worker_count must be at least 3."
  }
}

variable "master_server_type" {
  description = "Hetzner server type for masters (e.g. cpx32)"
  type        = string
}

variable "worker_server_type" {
  description = "Hetzner server type for workers (e.g. cpx42)"
  type        = string
}

variable "os_image" {
  description = "Hetzner OS image"
  type        = string
  default     = "ubuntu-24.04"
}

# ----- RKE2 -----------------------------------------------------------------

variable "kubernetes_version" {
  description = "RKE2 version tag"
  type        = string
}

variable "enable_cis_profile" {
  description = "RKE2 CIS profile toggle"
  type        = bool
}

variable "enable_hubble" {
  description = "Cilium Hubble toggle"
  type        = bool
}

variable "disable_kube_proxy" {
  description = "Cilium eBPF replaces kube-proxy"
  type        = bool
}

# ----- etcd snapshot --------------------------------------------------------

variable "etcd_snapshot_schedule" {
  description = "Cron expression for etcd snapshots"
  type        = string
  default     = "0 2 * * *"
}

variable "etcd_snapshot_retention" {
  description = "Local etcd snapshot retention"
  type        = number
  default     = 30
}

variable "etcd_s3_enabled" {
  description = "Ship etcd snapshots off-cluster to S3"
  type        = bool
  default     = false
}

variable "etcd_s3_endpoint" {
  description = "S3 endpoint URL"
  type        = string
  default     = ""
}

variable "etcd_s3_bucket" {
  description = "S3 bucket for etcd snapshots"
  type        = string
  default     = ""
}

variable "etcd_s3_region" {
  description = "S3 region"
  type        = string
  default     = ""
}

variable "etcd_s3_access_key" {
  description = "S3 access key"
  type        = string
  default     = ""
  sensitive   = true
}

variable "etcd_s3_secret_key" {
  description = "S3 secret key"
  type        = string
  default     = ""
  sensitive   = true
}
