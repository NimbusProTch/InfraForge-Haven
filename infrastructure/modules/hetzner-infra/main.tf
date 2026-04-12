# =============================================================================
#  iyziops — Hetzner base infrastructure
# =============================================================================
#  SSH key, private network, subnet, public firewall, and the single
#  tofu-managed load balancer that fronts both the Kubernetes API (6443) and
#  the Cilium Gateway (80/443). LB targets are attached in the environment
#  level (not here) because they reference server IDs.
#
#  Node-to-node traffic goes over the private network and is NOT filtered
#  by hcloud_firewall — Hetzner firewalls only apply to public ingress. That
#  is why this file contains no rules for VXLAN, kubelet, or the RKE2
#  supervisor port: cluster-internal traffic stays on 10.x and never touches
#  the public firewall.
# =============================================================================

resource "hcloud_ssh_key" "this" {
  name       = "${var.cluster_name}-${var.environment}"
  public_key = var.ssh_public_key
}

resource "hcloud_network" "this" {
  name     = "${var.cluster_name}-${var.environment}"
  ip_range = var.network_cidr
}

resource "hcloud_network_subnet" "this" {
  network_id   = hcloud_network.this.id
  type         = "cloud"
  network_zone = var.network_zone
  ip_range     = var.subnet_cidr
}

# -----------------------------------------------------------------------------
#  Public firewall
# -----------------------------------------------------------------------------
#  Rules are intentionally minimal. Everything else (kubelet, VXLAN, etcd,
#  RKE2 supervisor on 9345, LB → node traffic) is private-network only.
# -----------------------------------------------------------------------------
resource "hcloud_firewall" "this" {
  name = "${var.cluster_name}-${var.environment}"

  # SSH — operator shell access only
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.operator_cidrs
  }

  # Kubernetes API — operator kubectl (direct, bypassing the LB)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "6443"
    source_ips = var.operator_cidrs
  }

  # HTTP — public (Let's Encrypt HTTP-01 + tenant apps via Cilium Gateway)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTPS — public (tenant apps via Cilium Gateway)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

# -----------------------------------------------------------------------------
#  Load balancer — single public entry point
# -----------------------------------------------------------------------------
#  Listens on 6443/80/443. Targets (servers on private IPs) are attached in
#  the environment layer. Services use the private target IP via
#  use_private_ip = true on hcloud_load_balancer_target (see environments/).
# -----------------------------------------------------------------------------
resource "hcloud_load_balancer" "this" {
  name               = "${var.cluster_name}-${var.environment}"
  load_balancer_type = var.lb_type
  location           = var.location_primary
}

resource "hcloud_load_balancer_network" "this" {
  load_balancer_id = hcloud_load_balancer.this.id
  subnet_id        = hcloud_network_subnet.this.id
}

resource "hcloud_load_balancer_service" "k8s_api" {
  load_balancer_id = hcloud_load_balancer.this.id
  protocol         = "tcp"
  listen_port      = 6443
  destination_port = 6443

  health_check {
    protocol = "tcp"
    port     = 6443
    interval = 15
    timeout  = 10
    retries  = 3
  }
}

resource "hcloud_load_balancer_service" "http" {
  load_balancer_id = hcloud_load_balancer.this.id
  protocol         = "tcp"
  listen_port      = 80
  destination_port = var.gateway_http_nodeport

  health_check {
    protocol = "tcp"
    port     = var.gateway_http_nodeport
    interval = 15
    timeout  = 10
    retries  = 3
  }
}

resource "hcloud_load_balancer_service" "https" {
  load_balancer_id = hcloud_load_balancer.this.id
  protocol         = "tcp"
  listen_port      = 443
  destination_port = var.gateway_https_nodeport

  health_check {
    protocol = "tcp"
    port     = var.gateway_https_nodeport
    interval = 15
    timeout  = 10
    retries  = 3
  }
}
