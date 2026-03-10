# ============================================================
# Hetzner Cloud Infra Module
# ============================================================
# Management node (Rancher) + RKE2 cluster nodes
# Multi-AZ: Primary (Falkenstein) + Secondary (Nuremberg)
# ============================================================

locals {
  # Multi-AZ dağılımı: ilk 4 node primary, son 2 node secondary
  master_locations = [for i in range(var.master_count) : i < 2 ? var.location_primary : var.location_secondary]
  worker_locations = [for i in range(var.worker_count) : i < 2 ? var.location_primary : var.location_secondary]
}

# --- SSH Key ---
resource "hcloud_ssh_key" "haven" {
  name       = "haven-${var.environment}"
  public_key = file(var.ssh_public_key)
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
    direction = "in"
    protocol  = "tcp"
    port      = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Kubernetes API
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "6443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Rancher UI (HTTPS)
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTP (Let's Encrypt challenge)
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # RKE2 supervisor API
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "9345"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # NodePort range
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "30000-32767"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # VXLAN (Cilium)
  rule {
    direction = "in"
    protocol  = "udp"
    port      = "8472"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # etcd
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "2379-2380"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Kubelet
  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "10250"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

# --- Management Node (Rancher Server) ---
resource "hcloud_server" "management" {
  name        = "haven-mgmt-${var.environment}"
  server_type = var.management_server_type
  image       = var.os_image
  location    = var.location_primary
  ssh_keys    = [hcloud_ssh_key.haven.id]
  firewall_ids = [hcloud_firewall.haven.id]

  labels = {
    role        = "management"
    environment = var.environment
    project     = "haven"
  }
}

resource "hcloud_server_network" "management" {
  server_id  = hcloud_server.management.id
  network_id = hcloud_network.haven.id
}

# --- Master Nodes (RKE2 Control Plane) ---
resource "hcloud_server" "master" {
  count       = var.master_count
  name        = "haven-master-${var.environment}-${count.index + 1}"
  server_type = var.master_server_type
  image       = var.os_image
  location    = local.master_locations[count.index]
  ssh_keys    = [hcloud_ssh_key.haven.id]
  firewall_ids = [hcloud_firewall.haven.id]

  labels = {
    role        = "master"
    environment = var.environment
    project     = "haven"
    node_index  = tostring(count.index + 1)
  }
}

resource "hcloud_server_network" "master" {
  count      = var.master_count
  server_id  = hcloud_server.master[count.index].id
  network_id = hcloud_network.haven.id
}

# --- Worker Nodes (RKE2 Workers) ---
resource "hcloud_server" "worker" {
  count       = var.worker_count
  name        = "haven-worker-${var.environment}-${count.index + 1}"
  server_type = var.worker_server_type
  image       = var.os_image
  location    = local.worker_locations[count.index]
  ssh_keys    = [hcloud_ssh_key.haven.id]
  firewall_ids = [hcloud_firewall.haven.id]

  labels = {
    role        = "worker"
    environment = var.environment
    project     = "haven"
    node_index  = tostring(count.index + 1)
  }
}

resource "hcloud_server_network" "worker" {
  count      = var.worker_count
  server_id  = hcloud_server.worker[count.index].id
  network_id = hcloud_network.haven.id
}

# --- Load Balancer (API + Ingress) ---
resource "hcloud_load_balancer" "haven" {
  name               = "haven-lb-${var.environment}"
  load_balancer_type = "lb11"
  location           = var.location_primary
}

resource "hcloud_load_balancer_network" "haven" {
  load_balancer_id = hcloud_load_balancer.haven.id
  network_id       = hcloud_network.haven.id
}

# K8s API target (master nodes)
resource "hcloud_load_balancer_target" "master" {
  count            = var.master_count
  type             = "server"
  load_balancer_id = hcloud_load_balancer.haven.id
  server_id        = hcloud_server.master[count.index].id
}

# K8s API service
resource "hcloud_load_balancer_service" "k8s_api" {
  load_balancer_id = hcloud_load_balancer.haven.id
  protocol         = "tcp"
  listen_port      = 6443
  destination_port = 6443
}

# HTTP service (worker nodes üzerinden)
resource "hcloud_load_balancer_service" "http" {
  load_balancer_id = hcloud_load_balancer.haven.id
  protocol         = "tcp"
  listen_port      = 80
  destination_port = 80
}

# HTTPS service
resource "hcloud_load_balancer_service" "https" {
  load_balancer_id = hcloud_load_balancer.haven.id
  protocol         = "tcp"
  listen_port      = 443
  destination_port = 443
}
