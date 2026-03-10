output "management_ip" {
  description = "Rancher management node public IP"
  value       = hcloud_server.management.ipv4_address
}

output "master_ips" {
  description = "RKE2 master node public IP'leri"
  value       = hcloud_server.master[*].ipv4_address
}

output "worker_ips" {
  description = "RKE2 worker node public IP'leri"
  value       = hcloud_server.worker[*].ipv4_address
}

output "master_nodes" {
  description = "Master node detayları (rancher-cluster modülü için)"
  value = [for i, s in hcloud_server.master : {
    name       = s.name
    ip         = s.ipv4_address
    private_ip = hcloud_server_network.master[i].ip
    location   = s.location
  }]
}

output "worker_nodes" {
  description = "Worker node detayları (rancher-cluster modülü için)"
  value = [for i, s in hcloud_server.worker : {
    name       = s.name
    ip         = s.ipv4_address
    private_ip = hcloud_server_network.worker[i].ip
    location   = s.location
  }]
}

output "load_balancer_ip" {
  description = "Load balancer public IP"
  value       = hcloud_load_balancer.haven.ipv4
}

output "network_id" {
  description = "Private network ID"
  value       = hcloud_network.haven.id
}
