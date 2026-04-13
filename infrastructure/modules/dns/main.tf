# =============================================================================
#  iyziops — Cloudflare DNS
# =============================================================================
#  Three A records:
#    1. apex  (iyziops.com)        → ingress LB IP — UI entry point + apex
#    2. wildcard (*.iyziops.com)   → ingress LB IP — every platform subdomain
#                                    (argocd, api, app, harbor, grafana,
#                                    keycloak, etc.) and every tenant
#                                    subdomain. Wildcard cert covers them.
#    3. k8s   (k8s.iyziops.com)    → API LB IP — direct kubectl access only.
#                                    NOT covered by the wildcard cert (the
#                                    LB terminates TCP on 6443 directly to
#                                    kube-apiserver which presents its own
#                                    cluster CA cert).
#
#  The split exists because the ingress LB is CCM-adopted (carries 80/443
#  services for the Cilium Gateway) and the API LB is tofu-managed (carries
#  6443 only for kube-apiserver). They are two physically distinct Hetzner
#  load balancers with two distinct public IPs.
#
#  Proxy mode is OFF on every record because:
#    - cert-manager uses DNS-01 challenge; no Cloudflare proxy interference
#    - TLS termination happens in Cilium Envoy, not Cloudflare
# =============================================================================

data "cloudflare_zone" "this" {
  name = var.zone_name
}

resource "cloudflare_record" "apex" {
  zone_id = data.cloudflare_zone.this.id
  name    = "@"
  type    = "A"
  content = var.ingress_lb_ip
  ttl     = var.ttl
  proxied = false
  comment = var.comment
}

resource "cloudflare_record" "wildcard" {
  zone_id = data.cloudflare_zone.this.id
  name    = "*"
  type    = "A"
  content = var.ingress_lb_ip
  ttl     = var.ttl
  proxied = false
  comment = var.comment
}

resource "cloudflare_record" "k8s" {
  zone_id = data.cloudflare_zone.this.id
  name    = "k8s"
  type    = "A"
  content = var.api_lb_ip
  ttl     = var.ttl
  proxied = false
  comment = "${var.comment} — kube-apiserver (kubectl)"
}
