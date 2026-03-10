# ============================================================
# Haven Platform - Dev Environment (Hetzner Cloud)
# ============================================================
# Mimari:
#   Management: 1x CX31 (Rancher server)
#   Cluster:    3x CX31 master + 3x CX41 worker (RKE2)
#   Network:    Private network + Load Balancer + Firewall
#   Multi-AZ:   Falkenstein (4 node) + Nuremberg (2 node)
# ============================================================

# --- Hetzner Infra Module ---
module "hetzner_infra" {
  source = "../../modules/hetzner-infra"

  environment           = var.environment
  location_primary      = var.location_primary
  location_secondary    = var.location_secondary
  management_server_type = var.management_server_type
  master_server_type    = var.master_server_type
  worker_server_type    = var.worker_server_type
  master_count          = var.master_count
  worker_count          = var.worker_count
  ssh_public_key        = var.ssh_public_key
  network_cidr          = var.network_cidr
  subnet_cidr           = var.subnet_cidr
}

# --- Rancher Cluster Module ---
# Rancher kurulduktan sonra aktif edilecek (Phase 0.2)
# module "rancher_cluster" {
#   source = "../../modules/rancher-cluster"
#
#   depends_on = [module.hetzner_infra]
#
#   cluster_name       = "haven-${var.environment}"
#   kubernetes_version = var.kubernetes_version
#   master_nodes       = module.hetzner_infra.master_nodes
#   worker_nodes       = module.hetzner_infra.worker_nodes
# }
