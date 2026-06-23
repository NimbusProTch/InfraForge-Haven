# =============================================================================
#  iyziops — prod control-plane + worker nodes
# =============================================================================
#  Master / worker hcloud_server resources. Split out of hetzner.tf to keep
#  each file under the 200-line cap (iac-discipline Rule 5). Base infra, SSH
#  key, cluster token and the node-IP locals live in hetzner.tf; LB targets in
#  hetzner-lb-targets.tf. Every node has no public IPv4/IPv6 (Haven private-
#  networking) and a pinned private IP (DHCP-drift guard, see hetzner.tf locals).
# =============================================================================

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
  # from drifting the private IP on lease renewal — see the locals block
  # in hetzner.tf for the incident that motivated this.
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
  # See master block and hetzner.tf locals for the incident that motivated
  # pinning every node's private IP.
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
