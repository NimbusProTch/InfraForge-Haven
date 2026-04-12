# =============================================================================
#  iyziops — Hetzner base infrastructure (outputs)
# =============================================================================

output "load_balancer_id" {
  description = "Hetzner load balancer ID — used to attach master/worker targets"
  value       = hcloud_load_balancer.this.id
}

output "load_balancer_ipv4" {
  description = "Hetzner LB public IPv4 — DNS A record target and RKE2 tls-san"
  value       = hcloud_load_balancer.this.ipv4
}

output "load_balancer_private_ipv4" {
  description = "Hetzner LB private IPv4 (inside subnet_cidr) — used as tls-san for kubectl-in-cluster"
  value       = hcloud_load_balancer_network.this.ip
}

output "network_id" {
  description = "Private network ID — used to attach server networks"
  value       = hcloud_network.this.id
}

output "network_cidr" {
  description = "Private network CIDR"
  value       = hcloud_network.this.ip_range
}

output "subnet_id" {
  description = "Private subnet ID"
  value       = hcloud_network_subnet.this.id
}

output "subnet_cidr" {
  description = "Private subnet CIDR — used as Cilium ipv4NativeRoutingCIDR"
  value       = hcloud_network_subnet.this.ip_range
}

output "ssh_key_id" {
  description = "SSH key ID — referenced by hcloud_server.ssh_keys"
  value       = hcloud_ssh_key.this.id
}

output "firewall_id" {
  description = "Firewall ID — referenced by hcloud_server.firewall_ids"
  value       = hcloud_firewall.this.id
}
