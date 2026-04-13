# =============================================================================
#  iyziops — RKE2 readiness probe
# =============================================================================
#  Waits for the Kubernetes API to be reachable via the Hetzner LB. Uses
#  `data.http` with built-in retry so tofu apply blocks until the cluster
#  is usable.
#
#  Why a whole module for one data source? It keeps the environment layer
#  clean (one module call instead of an inline resource) and documents the
#  "cluster is ready" signal as an explicit module boundary.
# =============================================================================

data "http" "kube_api_ready" {
  url      = "https://${var.lb_ip}:6443/livez"
  insecure = true

  retry {
    attempts     = var.max_attempts
    max_delay_ms = var.max_delay_ms
    min_delay_ms = 5000
  }
}
