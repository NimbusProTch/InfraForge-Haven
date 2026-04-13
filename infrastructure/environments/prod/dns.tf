# =============================================================================
#  iyziops — prod Cloudflare DNS
# =============================================================================
#  Two LBs → three records:
#    apex (@)        → ingress LB
#    wildcard (*)    → ingress LB
#    api             → API LB
#
#  All records are created automatically by `tofu apply`; no manual dashboard
#  edits.
# =============================================================================

module "dns" {
  source = "../../modules/dns"

  zone_name     = var.platform_apex_domain
  ingress_lb_ip = module.hetzner_infra.load_balancer_ingress_ipv4
  api_lb_ip     = module.hetzner_infra.load_balancer_api_ipv4
}
