output "management_ip" {
  description = "Rancher management node public IP"
  value       = module.hetzner_infra.management_ip
}

output "master_ips" {
  description = "RKE2 master node public IP'leri"
  value       = module.hetzner_infra.master_ips
}

output "worker_ips" {
  description = "RKE2 worker node public IP'leri"
  value       = module.hetzner_infra.worker_ips
}

output "load_balancer_ip" {
  description = "Load balancer public IP"
  value       = module.hetzner_infra.load_balancer_ip
}
