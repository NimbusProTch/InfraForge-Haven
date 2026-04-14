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
#
#  LB topology (Option B / kube-hetzner pattern):
#    - api LB     : 6443, masters only, fully tofu-managed
#    - ingress LB : shell, no tofu services/targets, CCM adopts and
#                   reconciles 80/443 + targets after Cilium Gateway boots
# =============================================================================

# ----- SSH key (generated, written to logs/ for SCP) ------------------------
#  This pem is persistent, NOT scratch: it's required by `make kubeconfig`
#  to SCP the RKE2 kubeconfig from the first master. It lives under logs/
#  because logs/ is gitignored, so the private key never reaches git.

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

  cluster_name        = var.cluster_name
  environment         = var.environment
  ssh_public_key      = tls_private_key.cluster.public_key_openssh
  location_primary    = var.location_primary
  worker_location     = var.worker_location
  network_zone        = var.network_zone
  network_cidr        = var.network_cidr
  subnet_cidr         = var.subnet_cidr
  api_lb_type         = var.api_lb_type
  ingress_lb_type     = var.ingress_lb_type
  ingress_lb_location = var.location_primary
  operator_cidrs      = var.operator_cidrs
}

# ----- Reserve a stable private IP for the first master --------------------
#
#  The rke2-cluster module needs first_master_private_ip at render time so
#  joining masters and workers can use it as the supervisor endpoint. Hetzner
#  normally allocates private IPs dynamically, so we pin the first master
#  explicitly via the inline `network { ip = ... }` block on the master[0]
#  server resource below.
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

  ssh_keys = [module.hetzner_infra.ssh_key_id]

  user_data = count.index == 0 ? module.rke2_cluster.first_master_cloud_init : module.rke2_cluster.joining_master_cloud_init

  # Haven privatenetworking: masters have no public IPv4 / IPv6. They
  # reach the internet via the NAT box (hcloud_network_route default
  # gateway → 10.10.1.254) and are reachable from operators only via
  # the API LB (kubectl → 6443) or through the NAT box (SSH bastion).
  public_net {
    ipv4_enabled = false
    ipv6_enabled = false
  }

  # Inline network attachment — required when the server has no public
  # IPv4/IPv6, otherwise Hetzner refuses to start the VM with "no
  # public or private network interfaces found". The first master gets
  # a pinned IP matching local.first_master_private_ip so joining nodes
  # have a stable registration address.
  network {
    network_id = module.hetzner_infra.network_id
    ip         = count.index == 0 ? local.first_master_private_ip : null
  }

  labels = {
    role        = "master"
    cluster     = var.cluster_name
    environment = var.environment
  }

  # module.hetzner_infra includes hcloud_network_route.default_via_nat,
  # so this depends_on serializes master creation behind NAT readiness.
  depends_on = [
    module.hetzner_infra,
  ]
}

# ----- Worker nodes ---------------------------------------------------------

resource "hcloud_server" "worker" {
  count = var.worker_count

  name        = "${var.cluster_name}-worker-${count.index}"
  server_type = var.worker_server_type
  image       = var.os_image
  location    = var.worker_location

  ssh_keys = [module.hetzner_infra.ssh_key_id]

  user_data = module.rke2_cluster.worker_cloud_init

  # Haven privatenetworking: workers have no public IPv4 / IPv6.
  public_net {
    ipv4_enabled = false
    ipv6_enabled = false
  }

  # Inline network attachment (see master block) — required for
  # private-only servers to have at least one NIC at boot time.
  network {
    network_id = module.hetzner_infra.network_id
  }

  labels = {
    role        = "worker"
    cluster     = var.cluster_name
    environment = var.environment
  }

  depends_on = [
    module.hetzner_infra,
    hcloud_server.master,
  ]
}

# ----- API LB targets (masters only) ----------------------------------------
#  Worker targets do NOT belong on the API LB — workers don't run kube-apiserver.
#  Ingress LB targets are written by Hetzner CCM (the LB shell has
#  lifecycle ignore_changes = [targets]).

resource "hcloud_load_balancer_target" "api_master" {
  count = var.master_count

  load_balancer_id = module.hetzner_infra.load_balancer_api_id
  type             = "server"
  server_id        = hcloud_server.master[count.index].id
  use_private_ip   = true

  # hcloud_server.master now attaches the network inline, so the
  # private IP is present as soon as the server resource exists.
  depends_on = [hcloud_server.master]
}
