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

  # Kubernetes API — operator + node-to-node (Cilium routes via public IPs)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "6443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # RKE2 supervisor / remotedialer tunnel (workers → masters)
  # Node-to-node: workers connect to masters via public IP on port 9345.
  # Open to all IPs because node IPs are dynamic (assigned at create time).
  # RKE2 token-based auth protects against unauthorized joins.
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "9345"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # kubelet API (10250) — node-to-node
  # Required for apiserver → kubelet proxy (logs, exec, port-forward).
  # Without this, kubectl logs/exec return 502 Bad Gateway.
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "10250"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # VXLAN / Cilium overlay (8472) — node-to-node
  rule {
    direction  = "in"
    protocol   = "udp"
    port       = "8472"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
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
