# ============================================================
# Haven Platform - Dev Environment (Hetzner Cloud)
# ============================================================
# Single `tofu apply` creates everything:
#   1. Hetzner base infra (network, firewall, SSH, LB, mgmt node)
#   2. Wait for Rancher API to be ready
#   3. Bootstrap Rancher (rancher2 provider - Go native, no bash)
#   4. RKE2 cluster with Cilium CNI (via rancher-cluster module)
#   5. Master/Worker nodes with cloud-init registration
#   6. Longhorn storage (via Rancher marketplace, enable/disable)
#   7. Cert-Manager (auto HTTPS - Haven #12)
#   8. Rancher Monitoring (Prometheus + Grafana - Haven #14)
#   9. Rancher Logging (Banzai logging operator - Haven #13)
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

# --- 4. RKE2 Cluster (module: Cilium CNI + templates) ---
module "rancher_cluster" {
  source = "../../modules/rancher-cluster"
  providers = {
    rancher2 = rancher2.admin
  }

  cluster_name       = var.cluster_name
  kubernetes_version = var.kubernetes_version

  # Cilium CNI settings
  enable_hubble          = true
  cilium_operator_replicas = 1
  disable_kube_proxy     = true

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

# --- 8. Wait for Cluster Active ---
resource "null_resource" "wait_for_cluster_active" {
  depends_on = [
    hcloud_server.master,
    hcloud_server.worker,
    hcloud_server_network.master,
    hcloud_server_network.worker,
  ]

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    environment = {
      RANCHER_TOKEN = nonsensitive(rancher2_bootstrap.admin.token)
      RANCHER_URL   = nonsensitive(rancher2_bootstrap.admin.url)
      CLUSTER_ID    = module.rancher_cluster.cluster_id
      CLUSTER_NAME  = var.cluster_name
    }
    command = <<-EOT
      echo "Waiting for cluster $CLUSTER_NAME to become active..."
      for i in $(seq 1 180); do
        # Check if cluster K8s API is reachable via Rancher proxy
        HTTP_CODE=$(curl -sk -o /dev/null -w '%%{http_code}' \
          -H "Authorization: Bearer $RANCHER_TOKEN" \
          "$RANCHER_URL/k8s/clusters/$CLUSTER_ID/api/v1/namespaces" 2>/dev/null)
        echo "Attempt $i/180 - K8s API via Rancher proxy: HTTP $HTTP_CODE"
        if [ "$HTTP_CODE" = "200" ]; then
          echo "Cluster K8s API is reachable! Waiting 90s for catalog repos to sync..."
          sleep 90
          echo "Cluster is active!"
          exit 0
        fi
        sleep 10
      done
      echo "ERROR: Cluster did not become active in 30 minutes"
      exit 1
    EOT
  }
}

# --- 9. Longhorn Storage (via Rancher marketplace) ---
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

  depends_on = [null_resource.wait_for_cluster_active]
}

# --- 10. Cert-Manager (Haven Check #12: Auto HTTPS) ---
# Cert-Manager is not in rancher-charts, add Jetstack Helm repo
resource "rancher2_catalog_v2" "jetstack" {
  count      = var.enable_cert_manager ? 1 : 0
  provider   = rancher2.admin
  cluster_id = module.rancher_cluster.cluster_id
  name       = "jetstack"
  url        = "https://charts.jetstack.io"

  depends_on = [null_resource.wait_for_cluster_active]
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

  depends_on = [rancher2_catalog_v2.jetstack]
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

  depends_on = [null_resource.wait_for_cluster_active]
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

  depends_on = [rancher2_app_v2.monitoring_crd]
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

  depends_on = [null_resource.wait_for_cluster_active]
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

  depends_on = [rancher2_app_v2.logging_crd]
}
