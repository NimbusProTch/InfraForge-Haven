# ============================================================
# Hetzner Cloud Infra Module
# ============================================================
# Base infrastructure: SSH key, network, firewall, management
# node (Rancher), load balancer. Master/worker nodes are
# created at the environment level (need registration token).
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

# --- Firewall ---
resource "hcloud_firewall" "haven" {
  name = "haven-${var.environment}"

  # SSH
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Kubernetes API
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "6443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTPS (Rancher UI + Ingress)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTP (Let's Encrypt ACME challenge)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # RKE2 supervisor API
  # NOTE: Hetzner nodes communicate via public IPs by default.
  # Restricting to network_cidr breaks inter-node traffic.
  # TODO: Configure RKE2 to use private network, then restrict.
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "9345"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # VXLAN (Cilium overlay)
  rule {
    direction  = "in"
    protocol   = "udp"
    port       = "8472"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # etcd peer communication
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "2379-2380"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Kubelet API
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "10250"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

# --- Management Node (Rancher Server) ---
resource "hcloud_server" "management" {
  name         = "haven-mgmt-${var.environment}"
  server_type  = var.management_server_type
  image        = var.os_image
  location     = var.location_primary
  ssh_keys     = [hcloud_ssh_key.haven.id]
  firewall_ids = [hcloud_firewall.haven.id]

  user_data = templatefile("${path.module}/templates/management-cloud-init.yaml.tpl", {})

  labels = {
    role        = "management"
    environment = var.environment
    project     = "haven"
  }
}

resource "hcloud_server_network" "management" {
  server_id = hcloud_server.management.id
  subnet_id = hcloud_network_subnet.haven.id
}

# --- Load Balancer (K8s API + Ingress) ---
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

# HTTP service → gateway-proxy DaemonSet hostNetwork port 80
# Note: Cilium 1.16 L7LB doesn't propagate to NodePort BPF entries.
# gateway-proxy DaemonSet (haven-proxy ns) runs nginx with hostNetwork on port 80
# and proxies to the Cilium gateway ClusterIP (which has correct L7LB).
resource "hcloud_load_balancer_service" "http" {
  load_balancer_id = hcloud_load_balancer.haven.id
  protocol         = "tcp"
  listen_port      = 80
  destination_port = 80
}

# HTTPS service → gateway-proxy DaemonSet hostNetwork port 443
# nginx stream module does TCP passthrough to Cilium gateway Service port 443
# (same pattern as HTTP: nginx hostNetwork proxies to Cilium gateway ClusterIP)
resource "hcloud_load_balancer_service" "https" {
  load_balancer_id = hcloud_load_balancer.haven.id
  protocol         = "tcp"
  listen_port      = 443
  destination_port = 443
}
