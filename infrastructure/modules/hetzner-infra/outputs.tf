# =============================================================================
#  iyziops — Hetzner base infrastructure (outputs)
# =============================================================================

# ----- API load balancer (tofu-managed) -------------------------------------

output "load_balancer_api_id" {
  description = "Hetzner API LB ID — used to attach master targets in the environment layer"
  value       = hcloud_load_balancer.api.id
}

output "load_balancer_api_ipv4" {
  description = "Hetzner API LB public IPv4 — DNS A record target for api.iyziops.com and RKE2 tls-san"
  value       = hcloud_load_balancer.api.ipv4
}

output "load_balancer_api_private_ipv4" {
  description = "Hetzner API LB private IPv4 — used as tls-san for kubectl-in-cluster"
  value       = hcloud_load_balancer_network.api.ip
}

# ----- Ingress load balancer (CCM-adopted shell) ----------------------------

output "load_balancer_ingress_id" {
  description = "Hetzner ingress LB ID — CCM adopts this by name annotation on the Gateway Service"
  value       = hcloud_load_balancer.ingress.id
}

output "load_balancer_ingress_name" {
  description = "Hetzner ingress LB literal name — must match load-balancer.hetzner.cloud/name annotation on the Cilium Gateway"
  value       = hcloud_load_balancer.ingress.name
}

output "load_balancer_ingress_ipv4" {
  description = "Hetzner ingress LB public IPv4 — DNS A record target for apex + wildcard records"
  value       = hcloud_load_balancer.ingress.ipv4
}

# ----- Network --------------------------------------------------------------

output "network_id" {
  description = "Private network ID — used to attach server networks"
  value       = hcloud_network.this.id
}

output "network_name" {
  description = "Private network literal name — passed to Hetzner CCM via HCLOUD_NETWORK env"
  value       = hcloud_network.this.name
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
  description = "Private subnet CIDR — used as Cilium ipv4NativeRoutingCIDR if native routing ever enabled"
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
