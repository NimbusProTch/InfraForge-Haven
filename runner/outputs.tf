# =============================================================================
#  iyziops CI runner — outputs
# =============================================================================

output "runner_public_ipv4" {
  description = "Public IPv4 of the runner VM — used for SSH debugging"
  value       = hcloud_server.runner.ipv4_address
}

output "runner_name" {
  description = "Hetzner server name"
  value       = hcloud_server.runner.name
}

output "ssh_private_key_path" {
  description = "Filesystem path to the runner SSH private key (ed25519, 0600)"
  value       = local_sensitive_file.ssh_private_key.filename
}
