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

output "insecure_node_command" {
  description = "Rancher-generated node registration command (insecure, for self-signed certs)"
  value       = rancher2_cluster_v2.cluster.cluster_registration_token[0].insecure_node_command
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

output "harbor_values" {
  description = "Rendered Harbor Helm values"
  value = templatefile("${path.module}/templates/harbor-values.yaml.tpl", {
    harbor_host            = var.harbor_host
    harbor_admin_password  = var.harbor_admin_password
    registry_storage_size  = var.harbor_registry_storage_size
  })
  sensitive = true
}

output "minio_values" {
  description = "Rendered MinIO Helm values"
  value = templatefile("${path.module}/templates/minio-values.yaml.tpl", {
    minio_root_user     = var.minio_root_user
    minio_root_password = var.minio_root_password
    minio_storage_size  = var.minio_storage_size
    minio_console_host  = var.minio_console_host
    minio_api_host      = var.minio_api_host
  })
  sensitive = true
}

output "cnpg_values" {
  description = "Rendered CloudNativePG operator Helm values"
  value       = templatefile("${path.module}/templates/cnpg-values.yaml.tpl", {})
}

output "argocd_values" {
  description = "Rendered ArgoCD Helm values"
  value       = templatefile("${path.module}/templates/argocd-values.yaml.tpl", {})
}

output "keycloak_values" {
  description = "Rendered Keycloak Helm values"
  value = templatefile("${path.module}/templates/keycloak-values.yaml.tpl", {
    keycloak_admin_password = var.keycloak_admin_password
    keycloak_db_password    = var.keycloak_db_password
  })
  sensitive = true
}

output "external_dns_values" {
  description = "Rendered External-DNS Helm values"
  value = templatefile("${path.module}/templates/external-dns-values.yaml.tpl", {
    cloudflare_api_token = var.external_dns_cloudflare_token
    domain_filters       = var.external_dns_domain_filters
  })
  sensitive = true
}

output "redis_operator_values" {
  description = "Rendered Redis Operator Helm values"
  value       = templatefile("${path.module}/templates/redis-operator-values.yaml.tpl", {})
}

output "rabbitmq_operator_values" {
  description = "Rendered RabbitMQ Cluster Operator Helm values"
  value       = templatefile("${path.module}/templates/rabbitmq-operator-values.yaml.tpl", {})
}
