# =============================================================================
#  iyziops — Hetzner base infrastructure (variables)
# =============================================================================
#  No defaults for env-specific values. Everything comes from the environment
#  layer's tfvars file. Sensitive inputs are marked accordingly.
# =============================================================================

variable "cluster_name" {
  description = "Cluster identifier used as a resource name prefix (e.g. iyziops)"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}[a-z0-9]$", var.cluster_name))
    error_message = "cluster_name must be lowercase, 3-32 chars, start with a letter, end with a letter or digit."
  }
}

variable "environment" {
  description = "Environment identifier (e.g. prod). Single-env model — there is no dev."
  type        = string

  validation {
    condition     = contains(["prod"], var.environment)
    error_message = "environment must be one of: prod."
  }
}

variable "ssh_public_key" {
  description = "SSH public key (OpenSSH format) installed on every node"
  type        = string
}

variable "location_primary" {
  description = "Hetzner primary datacenter location for masters/workers (e.g. fsn1, nbg1, hel1)"
  type        = string
}

variable "network_zone" {
  description = "Hetzner network zone for the private subnet (e.g. eu-central)"
  type        = string
}

variable "network_cidr" {
  description = "CIDR of the private network that holds cluster nodes and LBs"
  type        = string
}

variable "subnet_cidr" {
  description = "CIDR of the private subnet (must be inside network_cidr)"
  type        = string
}

variable "api_lb_type" {
  description = "Hetzner load balancer type for the API LB (6443). lb11 is sufficient for control-plane traffic."
  type        = string

  validation {
    condition     = contains(["lb11", "lb21", "lb31"], var.api_lb_type)
    error_message = "api_lb_type must be one of: lb11, lb21, lb31."
  }
}

variable "ingress_lb_type" {
  description = "Hetzner load balancer type for the ingress LB (80/443). lb11 dev, lb21 customer-facing prod."
  type        = string

  validation {
    condition     = contains(["lb11", "lb21", "lb31"], var.ingress_lb_type)
    error_message = "ingress_lb_type must be one of: lb11, lb21, lb31."
  }
}

variable "ingress_lb_location" {
  description = "Hetzner datacenter location for the ingress LB. Should match location_primary unless multi-region."
  type        = string
}

variable "operator_cidrs" {
  description = "Allow-list CIDRs for public SSH (22) and direct kubectl (6443). Must not contain 0.0.0.0/0."
  type        = list(string)

  validation {
    condition     = !contains(var.operator_cidrs, "0.0.0.0/0") && !contains(var.operator_cidrs, "::/0")
    error_message = "operator_cidrs must not contain 0.0.0.0/0 or ::/0 — use explicit VPN/office CIDRs only."
  }

  validation {
    condition     = length(var.operator_cidrs) > 0
    error_message = "operator_cidrs cannot be empty — set your VPN or office egress CIDR."
  }
}
