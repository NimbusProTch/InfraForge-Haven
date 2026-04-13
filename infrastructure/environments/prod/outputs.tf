# =============================================================================
#  iyziops — prod outputs
# =============================================================================

output "load_balancer_api_ipv4" {
  description = "Hetzner API LB public IPv4 — kube-apiserver entry point (api.iyziops.com)"
  value       = module.hetzner_infra.load_balancer_api_ipv4
}

output "load_balancer_api_private_ipv4" {
  description = "Hetzner API LB private IPv4 — apiserver tls-san for in-cluster kubectl paths"
  value       = module.hetzner_infra.load_balancer_api_private_ipv4
}

output "load_balancer_ingress_ipv4" {
  description = "Hetzner ingress LB public IPv4 — Cloudflare apex + wildcard target. Populated by Hetzner CCM after Cilium Gateway boots."
  value       = module.hetzner_infra.load_balancer_ingress_ipv4
}

output "load_balancer_ingress_name" {
  description = "Hetzner ingress LB literal name — must match the load-balancer.hetzner.cloud/name annotation on iyziops-gateway"
  value       = module.hetzner_infra.load_balancer_ingress_name
}

output "first_master_public_ipv4" {
  description = "First master public IPv4 — used by `make kubeconfig` target"
  value       = hcloud_server.master[0].ipv4_address
}

output "first_master_private_ipv4" {
  description = "First master private IPv4 — stable registration address for joins"
  value       = local.first_master_private_ip
}

output "ssh_private_key_path" {
  description = "Filesystem path of the generated SSH private key (ed25519, 0600)"
  value       = local_sensitive_file.ssh_private_key.filename
}

output "master_public_ipv4s" {
  description = "Public IPv4 addresses of every master"
  value       = hcloud_server.master[*].ipv4_address
}

output "worker_public_ipv4s" {
  description = "Public IPv4 addresses of every worker"
  value       = hcloud_server.worker[*].ipv4_address
}

output "argocd_url" {
  description = "ArgoCD web UI URL (available after the root Application finishes syncing)"
  value       = "https://argocd.${var.platform_apex_domain}"
}

output "platform_url" {
  description = "iyziops platform UI URL"
  value       = "https://${var.platform_apex_domain}"
}

output "cluster_ready" {
  description = "True once the K8s API is reachable via the LB"
  value       = module.rke2_install.cluster_ready
}

output "dns_apex_fqdn" {
  description = "Apex DNS FQDN managed by Cloudflare"
  value       = module.dns.apex_fqdn
}

output "dns_wildcard_fqdn" {
  description = "Wildcard DNS FQDN managed by Cloudflare"
  value       = module.dns.wildcard_fqdn
}
