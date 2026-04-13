# =============================================================================
#  iyziops — RKE2 readiness probe (outputs)
# =============================================================================

output "cluster_ready" {
  description = "True when the K8s API returned an expected response (probe succeeded)"
  value       = data.http.kube_api_ready.status_code == 200 || data.http.kube_api_ready.status_code == 401
}

output "probe_status_code" {
  description = "Raw status code from the /livez probe — useful for debugging"
  value       = data.http.kube_api_ready.status_code
}
