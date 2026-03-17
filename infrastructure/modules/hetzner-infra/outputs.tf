output "management_ip" {
  description = "Rancher management node public IP"
  value       = hcloud_server.management.ipv4_address
}

output "load_balancer_ip" {
  description = "Load balancer public IP"
  value       = hcloud_load_balancer.haven.ipv4
}

output "network_id" {
  description = "Private network ID"
  value       = hcloud_network.haven.id
}

output "subnet_id" {
  description = "Subnet ID (for server_network dependency ordering)"
  value       = hcloud_network_subnet.haven.id
}

output "ssh_key_id" {
  description = "SSH key ID for cluster nodes"
  value       = hcloud_ssh_key.haven.id
}

output "firewall_id" {
  description = "Firewall ID for cluster nodes"
  value       = hcloud_firewall.haven.id
}

output "load_balancer_id" {
  description = "Load balancer ID for adding targets"
  value       = hcloud_load_balancer.haven.id
}
