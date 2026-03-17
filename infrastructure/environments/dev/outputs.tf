output "management_ip" {
  description = "Rancher management node public IP"
  value       = module.hetzner_infra.management_ip
}

output "master_ips" {
  description = "RKE2 master node public IPs"
  value       = hcloud_server.master[*].ipv4_address
}

output "worker_ips" {
  description = "RKE2 worker node public IPs"
  value       = hcloud_server.worker[*].ipv4_address
}

output "load_balancer_ip" {
  description = "Load balancer public IP"
  value       = module.hetzner_infra.load_balancer_ip
}

output "rancher_url" {
  description = "Rancher management URL"
  value       = "https://${local.rancher_server_dns}"
}

output "cluster_name" {
  description = "RKE2 cluster name"
  value       = module.rancher_cluster.cluster_name
}

output "harbor_url" {
  description = "Harbor registry URL"
  value       = var.enable_harbor ? "https://harbor.${module.hetzner_infra.load_balancer_ip}.sslip.io" : ""
}

output "minio_console_url" {
  description = "MinIO Console URL"
  value       = var.enable_minio ? "https://minio.${module.hetzner_infra.load_balancer_ip}.sslip.io" : ""
}

output "minio_api_url" {
  description = "MinIO S3 API URL"
  value       = var.enable_minio ? "https://s3.${module.hetzner_infra.load_balancer_ip}.sslip.io" : ""
}
