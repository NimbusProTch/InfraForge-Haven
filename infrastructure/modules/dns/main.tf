# =============================================================================
#  iyziops — Cloudflare DNS
# =============================================================================
#  Two A records point at the Hetzner LB public IP:
#    1. apex  (iyziops.com)        — UI entry point
#    2. wildcard (*.iyziops.com)   — every platform subdomain (argocd, api,
#                                    harbor, grafana, keycloak, etc.) and
#                                    every tenant subdomain
#
#  Proxy mode is OFF on both records because:
#    - Let's Encrypt HTTP-01 challenge needs a direct TCP path on :80
#    - TLS termination happens in Cilium Envoy, not Cloudflare
# =============================================================================

data "cloudflare_zone" "this" {
  name = var.zone_name
}

resource "cloudflare_record" "apex" {
  zone_id = data.cloudflare_zone.this.id
  name    = "@"
  type    = "A"
  content = var.lb_ip
  ttl     = var.ttl
  proxied = false
  comment = var.comment
}

resource "cloudflare_record" "wildcard" {
  zone_id = data.cloudflare_zone.this.id
  name    = "*"
  type    = "A"
  content = var.lb_ip
  ttl     = var.ttl
  proxied = false
  comment = var.comment
}
