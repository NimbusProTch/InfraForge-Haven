# ============================================================
# Hetzner Cloud Infra Module
# ============================================================
# Base infrastructure: SSH key, network, firewall, load balancer.
# No management node — RKE2 installed directly on master/worker.
# Firewall hardened: only HTTP/S + K8s API public, rest private.
# ============================================================

# --- SSH Key ---
resource "hcloud_ssh_key" "haven" {
  name       = "haven-${var.environment}"
  public_key = var.ssh_public_key
}

# --- Private Network ---
resource "hcloud_network" "haven" {
  name     = "haven-${var.environment}"
  ip_range = var.network_cidr
}

resource "hcloud_network_subnet" "haven" {
  network_id   = hcloud_network.haven.id
  type         = "cloud"
  network_zone = "eu-central"
  ip_range     = var.subnet_cidr
}

# --- Firewall (Hardened) ---
# Inter-node traffic flows over private network (node-ip config).
# Only public-facing ports open: SSH, HTTP/S, K8s API.
#
# H1b-1 (P4.1): operator-only ports (SSH 22, K8s API 6443, RKE2
# supervisor 9345) are restricted to var.operator_cidrs. Public web
# ports (80, 443) remain world-open because the platform serves customer
# tenant apps to the internet via Cilium Gateway API. Set operator_cidrs
# in terraform.tfvars to your VPN/office egress CIDRs before applying.
resource "hcloud_firewall" "haven" {
  name = "haven-${var.environment}"

  # SSH — operator only
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.operator_cidrs
  }

  # HTTP — public (Let's Encrypt ACME + tenant apps via Gateway API)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTPS — public (tenant apps via Gateway API)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Kubernetes API — operator only (via LB)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "6443"
    source_ips = var.operator_cidrs
  }

  # RKE2 supervisor / remotedialer tunnel (workers → masters)
  # Required: when node-external-ip is set, RKE2 advertises public IPs as
  # server endpoints. Workers connect to masters via public IP on port 9345
  # for the remotedialer WebSocket tunnel used by kubectl logs/exec.
  #
  # H1b-1 SECURITY: operator-only. Pre-fix this was world-open which was
  # a rogue worker join vector — anyone could attempt to register a node
  # against the supervisor. The architect's H0 audit flagged it as P0.
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "9345"
    source_ips = var.operator_cidrs
  }

  # NOTE: VXLAN (8472), etcd (2379-2380), kubelet API (10250) remain
  # private-only. Kubelet access goes through the remotedialer tunnel,
  # not directly from apiserver to kubelet via public IP.
}

# --- Load Balancer (K8s API + HTTP/S Ingress) ---
resource "hcloud_load_balancer" "haven" {
  name               = "haven-lb-${var.environment}"
  load_balancer_type = "lb11"
  location           = var.location_primary
}

resource "hcloud_load_balancer_network" "haven" {
  load_balancer_id = hcloud_load_balancer.haven.id
  subnet_id        = hcloud_network_subnet.haven.id
}

# K8s API service
resource "hcloud_load_balancer_service" "k8s_api" {
  load_balancer_id = hcloud_load_balancer.haven.id
  protocol         = "tcp"
  listen_port      = 6443
  destination_port = 6443
}

# HTTP service (Gateway API / ACME)
resource "hcloud_load_balancer_service" "http" {
  load_balancer_id = hcloud_load_balancer.haven.id
  protocol         = "tcp"
  listen_port      = 80
  destination_port = 80
}

# HTTPS service (Gateway API TLS termination)
resource "hcloud_load_balancer_service" "https" {
  load_balancer_id = hcloud_load_balancer.haven.id
  protocol         = "tcp"
  listen_port      = 443
  destination_port = 443
}
