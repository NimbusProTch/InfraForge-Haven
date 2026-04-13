# =============================================================================
#  iyziops — Hetzner base infrastructure
# =============================================================================
#  SSH key, private network, subnet, public firewall, and TWO load balancers:
#
#    1. api      — fully tofu-managed. Listens on 6443. Targets are the
#                  master nodes (attached in the environment layer).
#
#    2. ingress  — shell only. Tofu creates the LB and attaches it to the
#                  private network, but writes NO services and NO targets.
#                  Hetzner CCM adopts this LB by name (annotation on the
#                  Cilium Gateway → cilium-gateway-iyziops-gateway Service)
#                  and reconciles services + targets declaratively. The
#                  lifecycle{} block tells tofu to ignore CCM's writes.
#
#  This is the kube-hetzner / hcloud-k8s 2-LB pattern. CCM cannot share a
#  single LB with tofu-managed services: ReconcileHCLBServices deletes any
#  port not in the Service spec, so we keep the API LB completely separate.
#
#  Node-to-node traffic goes over the private network and is NOT filtered
#  by hcloud_firewall — Hetzner firewalls only apply to public ingress.
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
#
#  Note on 80/443: in the Option B architecture the ingress LB uses the
#  private network for LB → node traffic (use-private-ip: true via CCM
#  annotation) and the destination port is a NodePort, not 80/443. The
#  public 80/443 rules below are therefore not strictly required, but kept
#  open for direct-to-node debugging and as a no-op safety net.
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

  # Kubernetes API (6443). Public like 9345 because RKE2's agent-lb on every
  # worker and joining master discovers apiserver endpoints via the
  # kubernetes Service, which returns each master's ExternalIP. Apiserver
  # auth is TLS client certs + Bearer tokens, so the public exposure adds
  # no real attack surface beyond what the API LB already exposes on :6443.
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "6443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # RKE2 supervisor / agent-tunnel (websocket registration + remotedialer).
  # RKE2 dials peer masters via ExternalIP over public internet — even when
  # both nodes share a private network — because `node-external-ip` is set.
  # The tunnel is authenticated by the 64-char random cluster token.
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "9345"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTP — public (kept open as no-op safety net; LB→node uses private IP)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTPS — public (kept open as no-op safety net; LB→node uses private IP)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

# -----------------------------------------------------------------------------
#  API load balancer — tofu fully manages
# -----------------------------------------------------------------------------
#  Listens on 6443. Master targets are attached in the environment layer.
#  Services use the private target IP via use_private_ip = true on
#  hcloud_load_balancer_target (see environments/).
# -----------------------------------------------------------------------------
resource "hcloud_load_balancer" "api" {
  name               = "${var.cluster_name}-${var.environment}-api"
  load_balancer_type = var.api_lb_type
  location           = var.location_primary
}

resource "hcloud_load_balancer_network" "api" {
  load_balancer_id = hcloud_load_balancer.api.id
  subnet_id        = hcloud_network_subnet.this.id
}

resource "hcloud_load_balancer_service" "k8s_api" {
  load_balancer_id = hcloud_load_balancer.api.id
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

# -----------------------------------------------------------------------------
#  Ingress load balancer — shell only, CCM adopts and reconciles services
# -----------------------------------------------------------------------------
#  Tofu creates the LB resource and attaches it to the private network so
#  CCM has something to adopt. CCM finds it by the literal name (set via
#  the `load-balancer.hetzner.cloud/name` annotation on the Cilium Gateway
#  Service) and writes 80/443 services + node targets declaratively.
#
#  The lifecycle ignore_changes block prevents tofu from fighting CCM:
#    - targets: CCM writes the per-node targets
#    - labels[hcloud-ccm/service-uid]: CCM writes this on adoption
# -----------------------------------------------------------------------------
resource "hcloud_load_balancer" "ingress" {
  name               = "${var.cluster_name}-${var.environment}-ingress"
  load_balancer_type = var.ingress_lb_type
  location           = var.ingress_lb_location

  labels = {
    "iyziops.com/purpose" = "ingress"
  }

  lifecycle {
    ignore_changes = [
      target,
      labels["hcloud-ccm/service-uid"],
    ]
  }
}

resource "hcloud_load_balancer_network" "ingress" {
  load_balancer_id = hcloud_load_balancer.ingress.id
  subnet_id        = hcloud_network_subnet.this.id
}
