# =============================================================================
#  iyziops — API load-balancer targets
# =============================================================================
#  Registers the master nodes as targets on the API LB (port 6443). Split out
#  of hetzner.tf to keep each file under the 200-line cap (iac-discipline
#  Rule 5). Workers are NOT API-LB targets (they don't run kube-apiserver);
#  ingress-LB targets are written by Hetzner CCM, not tofu (the ingress LB
#  shell has lifecycle ignore_changes = [targets]).
# =============================================================================

resource "hcloud_load_balancer_target" "api_master" {
  count = var.master_count

  load_balancer_id = module.hetzner_infra.load_balancer_api_id
  type             = "server"
  server_id        = hcloud_server.master[count.index].id
  use_private_ip   = true

  # hcloud_server.master attaches the network inline, so the private IP is
  # present as soon as the server resource exists.
  depends_on = [hcloud_server.master]
}
