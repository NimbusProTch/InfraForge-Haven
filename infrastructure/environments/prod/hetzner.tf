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

# ----- Pin EVERY node's private IP so Hetzner DHCP cannot drift ------------
#
#  Lesson from 2026-04-15: leaving joining masters and workers at the
#  Hetzner auto-allocated IP (no `network.ip` field) combined with
#  `lifecycle { ignore_changes = [network] }` created a silent failure
#  mode. A DHCP lease renewal on Hetzner's side re-assigned two worker
#  IPs; kubelet's `--node-ip` (baked in at cloud-init via sed from
#  `ip addr show` at bootstrap time) became stale, so k8s `Node.InternalIP`
#  and the Cilium BPF tunnel maps pointed at the wrong physical server,
#  breaking cross-node pod networking for ~32 hours.
#
#  The upstream kube-hetzner module solves this by passing `var.private_ipv4`
#  down to its host module and setting `hcloud_server.network { ip = ... }`
#  explicitly for every node. We now do the same here, with an explicit
#  offset table so the current cluster's state (masters at /10, /4, /3 from
#  the original Hetzner DHCP allocation; workers at /5, /6, /7) is preserved
#  byte-for-byte. After this change `tofu plan` reports 0/0/0 on the
#  existing cluster; only a future cluster rebuild will use the pinned IPs
#  deterministically.
#
#  Going forward the offsets can be renumbered (e.g. masters 10/11/12,
#  workers 20/21/22) in a maintenance-window migration — THIS PR explicitly
#  does NOT do that, to avoid triggering `ForceNew` on the network block.

locals {
  # Historical DHCP-allocated offsets, pinned to match the current tofu
  # state so adding the `ip` field + removing `ignore_changes` is a no-op
  # on the live cluster. Migration to sequential offsets (10/11/12 and
  # 20/21/22) is a separate sprint.
  master_host_offsets = [10, 4, 3]
  worker_host_offsets = [5, 6, 7]
  master_private_ips  = [for o in local.master_host_offsets : cidrhost(var.subnet_cidr, o)]
  worker_private_ips  = [for o in local.worker_host_offsets : cidrhost(var.subnet_cidr, o)]

  # The RKE2 server URL pointed at by joining masters and workers.
  first_master_private_ip = local.master_private_ips[0]
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

  # Inline network attachment with an explicit pinned IP per master index.
  # Required when the server has no public IPv4/IPv6 (otherwise Hetzner
  # refuses to start the VM). Pinning every master prevents Hetzner DHCP
  # from drifting the private IP on lease renewal — see the local block
  # comment above for the incident that motivated this.
  network {
    network_id = module.hetzner_infra.network_id
    ip         = local.master_private_ips[count.index]
  }

  labels = {
    role        = "master"
    cluster     = var.cluster_name
    environment = var.environment
  }

  # ignore_changes [network] is NOT used here anymore: the IP is now
  # pinned explicitly via the local offset table, so there is no
  # DHCP-driven drift for tofu to ignore. A future rename of the offset
  # table IS destructive (ForceNew on the network block), and must be
  # done in a maintenance window with one-at-a-time drain-apply-rejoin.
  lifecycle {
    ignore_changes = [image, user_data, ssh_keys]
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

  # Inline network attachment with an explicit pinned IP per worker index.
  # See master block and local block comments above for the incident that
  # motivated pinning every node's private IP.
  network {
    network_id = module.hetzner_infra.network_id
    ip         = local.worker_private_ips[count.index]
  }

  labels = {
    role        = "worker"
    cluster     = var.cluster_name
    environment = var.environment
  }

  # ignore_changes [network] removed — see master block for rationale.
  lifecycle {
    ignore_changes = [image, user_data, ssh_keys]
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
