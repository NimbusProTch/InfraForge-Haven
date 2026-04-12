# =============================================================================
#  iyziops — prod Hetzner Cloud resources
# =============================================================================
#  Base Hetzner infra + master / worker servers + LB targets. The cloud-init
#  strings come from the rke2-cluster module (see rke2.tf).
#
#  Server numbering: the first master (index 0) is the bootstrap node — it
#  runs `cluster-init: true` and writes every Helm Controller manifest.
#  Joining masters (index 1..N) wait for the first master on port 9345.
#  Workers join the same way as agents.
# =============================================================================

# ----- SSH key (generated, written to logs/ for SCP) ------------------------
#  This pem is persistent, NOT scratch: it's required by `make kubeconfig`
#  to SCP the RKE2 kubeconfig from the first master. It lives under logs/
#  because logs/ is gitignored, so the private key never reaches git. Do
#  not delete it between tasks — see .claude/rules/logs-directory.md for
#  the task-end cleanup rule (it excludes this persistent file).

resource "tls_private_key" "cluster" {
  algorithm = "ED25519"
}

resource "local_sensitive_file" "ssh_private_key" {
  filename        = "${path.root}/../../../logs/iyziops-prod-ssh.pem"
  content         = tls_private_key.cluster.private_key_openssh
  file_permission = "0600"
}

# ----- Cluster token (generated, kept in state) -----------------------------

resource "random_password" "cluster_token" {
  length  = 64
  special = false
}

# ----- Base infra -----------------------------------------------------------

module "hetzner_infra" {
  source = "../../modules/hetzner-infra"

  cluster_name     = var.cluster_name
  environment      = var.environment
  ssh_public_key   = tls_private_key.cluster.public_key_openssh
  location_primary = var.location_primary
  network_zone     = var.network_zone
  network_cidr     = var.network_cidr
  subnet_cidr      = var.subnet_cidr
  lb_type          = var.lb_type
  operator_cidrs   = var.operator_cidrs
}

# ----- Reserve a stable private IP for the first master --------------------
#
#  The rke2-cluster module needs first_master_private_ip at render time so
#  joining masters and workers can use it as the supervisor endpoint. Hetzner
#  normally allocates private IPs dynamically, so we pin the first master
#  explicitly via hcloud_server_network.master[0].ip further down.
#
#  Offset 10 picks an address deep enough inside the subnet to be clear of
#  Hetzner's reserved low addresses (.1 gateway, .2-.4 reserved in some
#  zones). It must stay inside var.subnet_cidr.

locals {
  first_master_host_offset = 10
  first_master_private_ip  = cidrhost(var.subnet_cidr, local.first_master_host_offset)
}

# ----- Control plane nodes --------------------------------------------------

resource "hcloud_server" "master" {
  count = var.master_count

  name        = "${var.cluster_name}-master-${count.index}"
  server_type = var.master_server_type
  image       = var.os_image
  location    = var.location_primary

  ssh_keys     = [module.hetzner_infra.ssh_key_id]
  firewall_ids = [module.hetzner_infra.firewall_id]

  user_data = count.index == 0 ? module.rke2_cluster.first_master_cloud_init : module.rke2_cluster.joining_master_cloud_init

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  labels = {
    role        = "master"
    cluster     = var.cluster_name
    environment = var.environment
  }

  depends_on = [
    module.hetzner_infra,
  ]
}

# Attach masters to the private network. The first master gets a fixed
# alias IP matching local.first_master_private_ip so joining nodes have a
# stable registration address.
resource "hcloud_server_network" "master" {
  count = var.master_count

  server_id = hcloud_server.master[count.index].id
  subnet_id = module.hetzner_infra.subnet_id
  ip        = count.index == 0 ? local.first_master_private_ip : null
}

# ----- Worker nodes ---------------------------------------------------------

resource "hcloud_server" "worker" {
  count = var.worker_count

  name        = "${var.cluster_name}-worker-${count.index}"
  server_type = var.worker_server_type
  image       = var.os_image
  location    = var.location_primary

  ssh_keys     = [module.hetzner_infra.ssh_key_id]
  firewall_ids = [module.hetzner_infra.firewall_id]

  user_data = module.rke2_cluster.worker_cloud_init

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  labels = {
    role        = "worker"
    cluster     = var.cluster_name
    environment = var.environment
  }

  depends_on = [
    module.hetzner_infra,
    hcloud_server_network.master,
  ]
}

resource "hcloud_server_network" "worker" {
  count = var.worker_count

  server_id = hcloud_server.worker[count.index].id
  subnet_id = module.hetzner_infra.subnet_id
}

# ----- LB targets -----------------------------------------------------------

resource "hcloud_load_balancer_target" "master" {
  count = var.master_count

  load_balancer_id = module.hetzner_infra.load_balancer_id
  type             = "server"
  server_id        = hcloud_server.master[count.index].id
  use_private_ip   = true

  depends_on = [hcloud_server_network.master]
}

resource "hcloud_load_balancer_target" "worker" {
  count = var.worker_count

  load_balancer_id = module.hetzner_infra.load_balancer_id
  type             = "server"
  server_id        = hcloud_server.worker[count.index].id
  use_private_ip   = true

  depends_on = [hcloud_server_network.worker]
}
