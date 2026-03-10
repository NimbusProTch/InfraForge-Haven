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

output "cert_manager_values" {
  description = "Rendered Cert-Manager Helm values"
  value       = templatefile("${path.module}/templates/cert-manager-values.yaml.tpl", {})
}

output "monitoring_values" {
  description = "Rendered rancher-monitoring Helm values"
  value = templatefile("${path.module}/templates/monitoring-values.yaml.tpl", {
    retention_size          = var.monitoring_retention_size
    retention_days          = var.monitoring_retention_days
    prometheus_cpu_request  = var.prometheus_cpu_request
    prometheus_memory_request = var.prometheus_memory_request
    prometheus_memory_limit = var.prometheus_memory_limit
  })
}

output "logging_values" {
  description = "Rendered rancher-logging Helm values"
  value = templatefile("${path.module}/templates/logging-values.yaml.tpl", {
    fluentbit_cpu_request    = var.fluentbit_cpu_request
    fluentbit_memory_request = var.fluentbit_memory_request
    fluentbit_memory_limit   = var.fluentbit_memory_limit
    fluentd_cpu_request      = var.fluentd_cpu_request
    fluentd_memory_request   = var.fluentd_memory_request
    fluentd_memory_limit     = var.fluentd_memory_limit
  })
}
