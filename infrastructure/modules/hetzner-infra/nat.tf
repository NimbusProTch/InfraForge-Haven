# =============================================================================
#  iyziops — NAT box + default network route (cluster egress gateway)
# =============================================================================
#  Cluster masters and workers run with public IPv4 disabled (Haven
#  `privatenetworking` requirement). They still need outbound internet for:
#    - rke2 install script (get.rke2.io)
#    - container image pulls (Harbor + upstream mirrors)
#    - Helm chart downloads (ArgoCD bootstrap + Helm Controller)
#    - Cloudflare API (cert-manager DNS-01 solver)
#    - Let's Encrypt ACME endpoints
#    - Gateway API CRD bundle fetch (master-cloud-init runcmd)
#
#  This single cx22 box receives default-route traffic from the whole
#  subnet via hcloud_network_route and MASQUERADEs it out its public
#  interface. It is the only server in the module with public IPv4.
#
#  SPOF trade-off: acceptable for dev / single-cluster Phase 1. Phase 2
#  (prod on Cyso / Leafcloud) gets a HA NAT pair with keepalived VIP or
#  a provider-managed NAT service.
# =============================================================================

# -----------------------------------------------------------------------------
#  Firewall — NAT box is the only server with a public IPv4, so operator
#  SSH + ICMP echo are the only inbound rules. Everything else arrives
#  from the private network (unfiltered by Hetzner firewalls).
# -----------------------------------------------------------------------------
resource "hcloud_firewall" "nat" {
  name = "${var.cluster_name}-${var.environment}-nat"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.operator_cidrs
  }

  rule {
    direction  = "in"
    protocol   = "icmp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

# -----------------------------------------------------------------------------
#  NAT box server
# -----------------------------------------------------------------------------
resource "hcloud_server" "nat" {
  name     = "${var.cluster_name}-${var.environment}-nat"
  location = var.location_primary
  # cpx22 (AMD, 2 vCPU / 4 GB / 80 GB) — cheapest *new-generation*
  # cpx-series type orderable in fsn1 as of 2026-04. The old cpxN1
  # family (cpx11/cpx21/cpx31...) is still listed by server-type but
  # Hetzner blocks new orders for them in most EU locations. The new
  # cpxN2 family (cpx22/cpx32/cpx42/cpx52) replaces it; cluster masters
  # run cpx32 and workers run cpx42 from the same generation.
  server_type = "cpx22"
  image       = "ubuntu-24.04"
  ssh_keys     = [hcloud_ssh_key.this.id]
  firewall_ids = [hcloud_firewall.nat.id]

  user_data = templatefile("${path.module}/templates/nat-cloud-init.yaml.tpl", {
    private_subnet_cidr = var.network_cidr
  })

  public_net {
    ipv4_enabled = true
    ipv6_enabled = false
  }

  labels = {
    role        = "nat"
    cluster     = var.cluster_name
    environment = var.environment
  }

  depends_on = [hcloud_network_subnet.this]
}

# -----------------------------------------------------------------------------
#  Pin the NAT box to a stable private IP (10.10.1.254) so the network
#  route gateway target is predictable.
# -----------------------------------------------------------------------------
resource "hcloud_server_network" "nat" {
  server_id = hcloud_server.nat.id
  subnet_id = hcloud_network_subnet.this.id
  # 254 = last usable host in a /24, clear of the Hetzner gateway at .1
  # and of first_master_private_ip which the environment layer pins to
  # cidrhost(subnet, 10).
  ip = cidrhost(var.subnet_cidr, 254)
}

# -----------------------------------------------------------------------------
#  Default route — sends 0.0.0.0/0 from the subnet to the NAT box. Hetzner
#  enforces that the gateway IP belongs to a resource attached to the
#  network, hence the depends_on.
# -----------------------------------------------------------------------------
resource "hcloud_network_route" "default_via_nat" {
  network_id  = hcloud_network.this.id
  destination = "0.0.0.0/0"
  gateway     = hcloud_server_network.nat.ip

  depends_on = [hcloud_server_network.nat]
}
