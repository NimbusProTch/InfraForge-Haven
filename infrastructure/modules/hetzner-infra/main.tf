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
resource "hcloud_firewall" "haven" {
  name = "haven-${var.environment}"

  # SSH (restricted to operator IPs in production)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTP (Let's Encrypt ACME + public services)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTPS (public services via Gateway API)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Kubernetes API (through LB, restrict in production)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "6443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # RKE2 supervisor / remotedialer tunnel (workers → masters)
  # Required: when node-external-ip is set, RKE2 advertises public IPs as
  # server endpoints. Workers connect to masters via public IP on port 9345
  # for the remotedialer WebSocket tunnel used by kubectl logs/exec.
  # Without this, all kubectl logs/exec calls return 502 Bad Gateway.
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "9345"
    source_ips = ["0.0.0.0/0", "::/0"]
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
