# =============================================================================
#  iyziops — RKE2 cluster (etcd snapshot variables)
# =============================================================================

variable "etcd_snapshot_schedule" {
  description = "Cron expression for automated etcd snapshots"
  type        = string
  default     = "0 2 * * *"
}

variable "etcd_snapshot_retention" {
  description = "Number of local etcd snapshots to retain"
  type        = number
  default     = 30
}

variable "etcd_s3_enabled" {
  description = "Ship etcd snapshots to an off-cluster S3 bucket (true for real DR)"
  type        = bool
  default     = false
}

variable "etcd_s3_endpoint" {
  description = "S3 endpoint URL for etcd snapshots"
  type        = string
  default     = ""
}

variable "etcd_s3_bucket" {
  description = "S3 bucket name for etcd snapshots"
  type        = string
  default     = ""
}

variable "etcd_s3_region" {
  description = "S3 region for etcd snapshots"
  type        = string
  default     = ""
}

variable "etcd_s3_access_key" {
  description = "S3 access key for etcd snapshots"
  type        = string
  default     = ""
  sensitive   = true
}

variable "etcd_s3_secret_key" {
  description = "S3 secret key for etcd snapshots"
  type        = string
  default     = ""
  sensitive   = true
}
