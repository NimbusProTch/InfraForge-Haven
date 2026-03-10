output "cluster_id" {
  description = "Rancher v1 cluster ID (used by rancher2_app_v2)"
  value       = rancher2_cluster_v2.cluster.cluster_v1_id
}

output "cluster_name" {
  description = "Cluster name"
  value       = rancher2_cluster_v2.cluster.name
}

output "registration_token" {
  description = "Node registration token for cloud-init"
  value       = rancher2_cluster_v2.cluster.cluster_registration_token[0].token
  sensitive   = true
}

# Rendered Helm values for downstream use
output "longhorn_values" {
  description = "Rendered Longhorn Helm values"
  value = templatefile("${path.module}/templates/longhorn-values.yaml.tpl", {
    replica_count = var.longhorn_replica_count
  })
}
