# ============================================================
# Haven Platform - Dev Environment (Hetzner Cloud)
# ============================================================
# Single `tofu apply` creates everything:
#   1. Hetzner base infra (network, firewall, SSH, LB, mgmt node)
#   2. Wait for Rancher API to be ready
#   3. Bootstrap Rancher (rancher2 provider - Go native, no bash)
#   4. Create RKE2 cluster definition
#   5. Master/Worker nodes with cloud-init registration
# ============================================================

locals {
  # Multi-AZ distribution: first 2 nodes primary, rest secondary
  master_locations = [for i in range(var.master_count) : i < 2 ? var.location_primary : var.location_secondary]
  worker_locations = [for i in range(var.worker_count) : i < 2 ? var.location_primary : var.location_secondary]
}

# --- 1. Base Infrastructure ---
module "hetzner_infra" {
  source = "../../modules/hetzner-infra"

  environment            = var.environment
  location_primary       = var.location_primary
  location_secondary     = var.location_secondary
  management_server_type = var.management_server_type
  ssh_public_key         = var.ssh_public_key
  network_cidr           = var.network_cidr
  subnet_cidr            = var.subnet_cidr

  # Rancher cloud-init
  rancher_bootstrap_password = var.rancher_bootstrap_password
  rancher_version            = var.rancher_version
}

# --- 2. Wait for Rancher API ---
resource "null_resource" "wait_for_rancher" {
  depends_on = [module.hetzner_infra]

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      echo "Waiting for Rancher at https://${module.hetzner_infra.management_ip}..."
      for i in $(seq 1 120); do
        if curl -sk "https://${module.hetzner_infra.management_ip}/ping" 2>/dev/null | grep -q pong; then
          echo "Rancher is ready!"
          exit 0
        fi
        echo "Attempt $i/120..."
        sleep 5
      done
      echo "ERROR: Rancher did not become ready in 10 minutes"
      exit 1
    EOT
  }
}

# --- 3. Bootstrap Rancher (Go native - no bash password issues) ---
resource "rancher2_bootstrap" "admin" {
  provider         = rancher2.bootstrap
  initial_password = var.rancher_bootstrap_password
  password         = var.rancher_admin_password

  depends_on = [null_resource.wait_for_rancher]
}

# --- 4. Create RKE2 Cluster Definition ---
resource "rancher2_cluster_v2" "haven" {
  provider           = rancher2.admin
  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version

  rke_config {
    machine_global_config = yamlencode({
      cni     = "none" # Cilium installed separately
      disable = ["rke2-ingress-nginx"]
    })
  }
}

# --- 5. Master Nodes (cloud-init with registration token) ---
resource "hcloud_server" "master" {
  count        = var.master_count
  name         = "haven-master-${var.environment}-${count.index + 1}"
  server_type  = var.master_server_type
  image        = var.os_image
  location     = local.master_locations[count.index]
  ssh_keys     = [module.hetzner_infra.ssh_key_id]
  firewall_ids = [module.hetzner_infra.firewall_id]

  user_data = templatefile("${path.module}/templates/node-cloud-init.yaml.tpl", {
    rancher_ip         = module.hetzner_infra.management_ip
    registration_token = rancher2_cluster_v2.haven.cluster_registration_token[0].token
    node_roles         = "--etcd --controlplane"
  })

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
  network_id = module.hetzner_infra.network_id
}

# --- 6. Worker Nodes (cloud-init with registration token) ---
resource "hcloud_server" "worker" {
  count        = var.worker_count
  name         = "haven-worker-${var.environment}-${count.index + 1}"
  server_type  = var.worker_server_type
  image        = var.os_image
  location     = local.worker_locations[count.index]
  ssh_keys     = [module.hetzner_infra.ssh_key_id]
  firewall_ids = [module.hetzner_infra.firewall_id]

  user_data = templatefile("${path.module}/templates/node-cloud-init.yaml.tpl", {
    rancher_ip         = module.hetzner_infra.management_ip
    registration_token = rancher2_cluster_v2.haven.cluster_registration_token[0].token
    node_roles         = "--worker"
  })

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
  network_id = module.hetzner_infra.network_id
}

# --- 7. Load Balancer Targets (master nodes) ---
resource "hcloud_load_balancer_target" "master" {
  count            = var.master_count
  type             = "server"
  load_balancer_id = module.hetzner_infra.load_balancer_id
  server_id        = hcloud_server.master[count.index].id
}
