# =============================================================================
#  iyziops — Cloudflare DNS (outputs)
# =============================================================================

output "zone_id" {
  description = "Cloudflare zone ID — used by cert-manager DNS-01 solver"
  value       = data.cloudflare_zone.this.id
}

output "apex_record_id" {
  description = "ID of the apex A record"
  value       = cloudflare_record.apex.id
}

output "wildcard_record_id" {
  description = "ID of the wildcard A record"
  value       = cloudflare_record.wildcard.id
}

output "apex_fqdn" {
  description = "Fully qualified domain name of the apex record"
  value       = cloudflare_record.apex.hostname
}

output "wildcard_fqdn" {
  description = "Fully qualified domain name of the wildcard record"
  value       = cloudflare_record.wildcard.hostname
}
