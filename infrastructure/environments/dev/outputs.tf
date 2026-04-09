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

output "cluster_name" {
  description = "RKE2 cluster name"
  value       = var.cluster_name
}

output "kubeconfig_path" {
  description = "Path to kubeconfig file"
  value       = local_sensitive_file.kubeconfig.filename
}

output "harbor_url" {
  description = "Harbor registry URL"
  # H1e: HTTPS — TLS termination at Cilium Gateway, intra-cluster plaintext.
  # See helm-values/harbor.yaml header comment for the chain.
  value       = var.enable_harbor ? "https://${local.harbor_host}" : ""
}

output "argocd_url" {
  description = "ArgoCD URL"
  value       = var.enable_argocd ? "https://${local.argocd_host}" : ""
}

output "keycloak_url" {
  description = "Keycloak URL"
  value       = var.enable_keycloak ? "https://${local.keycloak_host}" : ""
}

output "everest_url" {
  description = "Percona Everest URL"
  value       = var.enable_everest ? "https://${local.everest_host}" : ""
}
