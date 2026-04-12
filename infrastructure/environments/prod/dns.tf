# =============================================================================
#  iyziops — prod Cloudflare DNS
# =============================================================================
#  Apex + wildcard A records → LB public IPv4. Both records are created
#  automatically by `tofu apply`; no manual dashboard edits.
# =============================================================================

module "dns" {
  source = "../../modules/dns"

  zone_name = var.platform_apex_domain
  lb_ip     = module.hetzner_infra.load_balancer_ipv4
}
