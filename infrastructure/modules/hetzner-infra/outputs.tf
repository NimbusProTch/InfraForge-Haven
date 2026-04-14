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

# ----- NAT box --------------------------------------------------------------

output "nat_public_ipv4" {
  description = "NAT box public IPv4 — the single operator-accessible bastion"
  value       = hcloud_server.nat.ipv4_address
}

output "nat_private_ipv4" {
  description = "NAT box private IPv4 — gateway of the subnet default route"
  value       = hcloud_server_network.nat.ip
}

output "network_route_id" {
  description = "Default network route ID — cluster servers depend on this via the module dependency graph so they boot after egress is available"
  value       = hcloud_network_route.default_via_nat.id
}

output "worker_zone" {
  description = "Hetzner datacenter where worker nodes run — provides topology.kubernetes.io/zone distinct from the master zone (Haven infraMultiAZ)"
  value       = var.worker_location
}
