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
  value       = "https://${module.hetzner_infra.management_ip}"
}

output "cluster_name" {
  description = "RKE2 cluster name"
  value       = rancher2_cluster_v2.haven.name
}
