# =============================================================================
#  iyziops — Cloudflare DNS (variables)
# =============================================================================

variable "zone_name" {
  description = "Cloudflare DNS zone apex (e.g. iyziops.com)"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]+[a-z0-9]$", var.zone_name))
    error_message = "zone_name must be a valid lowercase domain (e.g. iyziops.com)."
  }
}

variable "ingress_lb_ip" {
  description = "Hetzner ingress LB public IPv4 — target for apex (@) and wildcard (*) A records. This is the LB CCM adopts and writes 80/443 services on; all platform/tenant subdomains resolve here."
  type        = string

  validation {
    condition     = can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}$", var.ingress_lb_ip))
    error_message = "ingress_lb_ip must be a valid IPv4 address."
  }
}

variable "api_lb_ip" {
  description = "Hetzner API LB public IPv4 — target for the api.iyziops.com record (kubectl access)."
  type        = string

  validation {
    condition     = can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}$", var.api_lb_ip))
    error_message = "api_lb_ip must be a valid IPv4 address."
  }
}

variable "ttl" {
  description = "TTL for DNS records (1 = Cloudflare auto)"
  type        = number
  default     = 1
}

variable "comment" {
  description = "Comment attached to each DNS record — helps humans identify tofu-managed entries"
  type        = string
  default     = "Managed by OpenTofu — iyziops platform"
}
