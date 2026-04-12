# =============================================================================
#  iyziops — RKE2 readiness probe (variables)
# =============================================================================

variable "lb_ip" {
  description = "Hetzner LB public IPv4 — the fixed registration address for the K8s API"
  type        = string
}

variable "max_attempts" {
  description = "Maximum retry attempts (at max_delay_ms each) before failing"
  type        = number
  default     = 180
}

variable "max_delay_ms" {
  description = "Maximum delay between retries in milliseconds (~ 10s)"
  type        = number
  default     = 10000
}
