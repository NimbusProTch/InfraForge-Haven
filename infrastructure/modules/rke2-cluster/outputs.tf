# ============================================================
# RKE2 Cluster Module - Outputs
# ============================================================

output "first_master_cloud_init" {
  description = "Cloud-init config for the first master (cluster bootstrap)"
  value       = local.master_cloud_init
  sensitive   = true
}

output "joining_master_cloud_init" {
  description = "Cloud-init config for additional masters (joining)"
  value       = local.joining_master_cloud_init
  sensitive   = true
}

output "worker_cloud_init" {
  description = "Cloud-init config for worker nodes"
  value       = local.worker_cloud_init
  sensitive   = true
}
