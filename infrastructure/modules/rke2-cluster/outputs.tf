# =============================================================================
#  iyziops — RKE2 cluster (outputs)
# =============================================================================

output "first_master_cloud_init" {
  description = "Cloud-init for the bootstrap master (cluster-init + all Helm Controller manifests)"
  value       = local.first_master_cloud_init
  sensitive   = true
}

output "joining_master_cloud_init" {
  description = "Cloud-init for additional masters (join via first master, no manifests)"
  value       = local.joining_master_cloud_init
  sensitive   = true
}

output "worker_cloud_init" {
  description = "Cloud-init for agent nodes"
  value       = local.worker_cloud_init
  sensitive   = true
}
