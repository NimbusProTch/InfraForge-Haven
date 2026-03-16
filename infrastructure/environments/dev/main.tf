# ============================================================
# Haven Platform - Dev Environment (Hetzner Cloud)
# ============================================================
# Single `tofu apply` creates everything:
#   1. Hetzner base infra (network, firewall, SSH, LB, mgmt node)
#   2. Wait for Rancher API (K3s + Helm install via cloud-init)
#   3. Bootstrap Rancher (rancher2 provider - Go native)
#   4. RKE2 cluster with Cilium CNI (via rancher-cluster module)
#   5. Master/Worker nodes with cloud-init registration
#   6. Wait for cluster active (rancher2_cluster_sync - native)
#   7. Longhorn storage (via Rancher marketplace)
#   8. Cert-Manager (auto HTTPS - Haven #12)
#   9. Rancher Monitoring (Prometheus + Grafana - Haven #14)
#  10. Rancher Logging (Banzai logging operator - Haven #13)
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

  # Rancher on K3s (production-grade, not Docker)
  rancher_bootstrap_password = var.rancher_bootstrap_password
  rancher_version            = var.rancher_version
  rancher_chart_version      = var.rancher_chart_version
  k3s_version                = var.k3s_version
}

# --- 2. Wait for Rancher API (K3s + Helm takes longer than Docker) ---
resource "terraform_data" "wait_for_rancher" {
  triggers_replace = [module.hetzner_infra.management_ip]

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      RANCHER_URL="https://${module.hetzner_infra.management_ip}"
      echo "Waiting for Rancher at $RANCHER_URL (K3s + Helm install)..."
      echo "This takes ~10-15 minutes for K3s + cert-manager + Rancher..."
      BACKOFF=10
      for i in $(seq 1 120); do
        if curl -sk "$RANCHER_URL/ping" 2>/dev/null | grep -q pong; then
          echo "Rancher is ready after $i attempts!"
          exit 0
        fi
        echo "Attempt $i/120 (sleep $BACKOFF s)..."
        sleep $BACKOFF
        if [ "$BACKOFF" -lt 20 ]; then
          BACKOFF=$((BACKOFF + 1))
        fi
      done
      echo "ERROR: Rancher did not become ready in 20+ minutes"
      exit 1
    EOT
  }
}

# --- 3. Bootstrap Rancher (Go native - no bash password issues) ---
resource "rancher2_bootstrap" "admin" {
  provider         = rancher2.bootstrap
  initial_password = var.rancher_bootstrap_password
  password         = var.rancher_admin_password

  depends_on = [terraform_data.wait_for_rancher]
}

# --- 4. RKE2 Cluster (module: Cilium CNI + templates) ---
module "rancher_cluster" {
  source = "../../modules/rancher-cluster"
  providers = {
    rancher2 = rancher2.admin
  }

  cluster_name       = var.cluster_name
  kubernetes_version = var.kubernetes_version

  # Cilium CNI settings
  enable_hubble            = true
  cilium_operator_replicas = 1
  disable_kube_proxy       = true

  # Longhorn values (rendered by module, used below)
  longhorn_replica_count = var.worker_count >= 3 ? 3 : var.worker_count
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
    registration_token = module.rancher_cluster.registration_token
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
    registration_token = module.rancher_cluster.registration_token
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

# --- 8. Wait for Cluster Active (native rancher2_cluster_sync) ---
# Replaces fragile null_resource + bash curl loops with Go-native wait
resource "rancher2_cluster_sync" "cluster" {
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  wait_catalogs = true
  state_confirm = 3

  timeouts {
    create = "45m"
    update = "45m"
  }

  depends_on = [
    hcloud_server.master,
    hcloud_server.worker,
    hcloud_server_network.master,
    hcloud_server_network.worker,
  ]
}

# --- 9. Longhorn Storage (via Rancher marketplace) ---
# Longhorn is installed FIRST - other apps depend on it for destroy ordering
# Destroy order: monitoring/logging/cert-manager → then Longhorn (slowest)
resource "rancher2_app_v2" "longhorn" {
  count         = var.enable_longhorn ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "longhorn"
  namespace     = "longhorn-system"
  repo_name     = "rancher-charts"
  chart_name    = "longhorn"
  chart_version = var.longhorn_version

  values = module.rancher_cluster.longhorn_values

  timeouts {
    create = "15m"
    update = "15m"
    delete = "20m"
  }

  depends_on = [rancher2_cluster_sync.cluster]
}

# --- 10. Cert-Manager (Haven Check #12: Auto HTTPS) ---
# Cert-Manager is not in rancher-charts, add Jetstack Helm repo
resource "rancher2_catalog_v2" "jetstack" {
  count      = var.enable_cert_manager ? 1 : 0
  provider   = rancher2.admin
  cluster_id = module.rancher_cluster.cluster_id
  name       = "jetstack"
  url        = "https://charts.jetstack.io"

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "cert_manager" {
  count         = var.enable_cert_manager ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "cert-manager"
  namespace     = "cert-manager"
  repo_name     = "jetstack"
  chart_name    = "cert-manager"
  chart_version = var.cert_manager_version

  values = module.rancher_cluster.cert_manager_values

  timeouts {
    create = "10m"
    update = "10m"
    delete = "10m"
  }

  # Destroy: cert-manager before Longhorn
  depends_on = [rancher2_catalog_v2.jetstack, rancher2_app_v2.longhorn]
}

# --- 11. Rancher Monitoring (Haven Check #14: Metrics + Grafana) ---
# CRDs must be installed first
resource "rancher2_app_v2" "monitoring_crd" {
  count         = var.enable_monitoring ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "rancher-monitoring-crd"
  namespace     = "cattle-monitoring-system"
  repo_name     = "rancher-charts"
  chart_name    = "rancher-monitoring-crd"
  chart_version = var.monitoring_version

  timeouts {
    create = "10m"
    update = "10m"
    delete = "10m"
  }

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "monitoring" {
  count         = var.enable_monitoring ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "rancher-monitoring"
  namespace     = "cattle-monitoring-system"
  repo_name     = "rancher-charts"
  chart_name    = "rancher-monitoring"
  chart_version = var.monitoring_version

  values = module.rancher_cluster.monitoring_values

  timeouts {
    create = "15m"
    update = "15m"
    delete = "15m"
  }

  # Destroy: monitoring before Longhorn
  depends_on = [rancher2_app_v2.monitoring_crd, rancher2_app_v2.longhorn]
}

# --- 12. Rancher Logging (Haven Check #13: Log aggregation) ---
# CRDs must be installed first
resource "rancher2_app_v2" "logging_crd" {
  count         = var.enable_logging ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "rancher-logging-crd"
  namespace     = "cattle-logging-system"
  repo_name     = "rancher-charts"
  chart_name    = "rancher-logging-crd"
  chart_version = var.logging_version

  timeouts {
    create = "10m"
    update = "10m"
    delete = "10m"
  }

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "logging" {
  count         = var.enable_logging ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "rancher-logging"
  namespace     = "cattle-logging-system"
  repo_name     = "rancher-charts"
  chart_name    = "rancher-logging"
  chart_version = var.logging_version

  values = module.rancher_cluster.logging_values

  timeouts {
    create = "15m"
    update = "15m"
    delete = "15m"
  }

  # Destroy: logging before Longhorn
  depends_on = [rancher2_app_v2.logging_crd, rancher2_app_v2.longhorn]
}
