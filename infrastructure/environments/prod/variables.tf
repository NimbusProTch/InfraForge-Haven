# =============================================================================
#  iyziops — prod (credentials + identity + Hetzner base)
# =============================================================================
#  Sensitive values come from Keychain via TF_VAR_* env vars (see the
#  `iyziops-env` function in ~/.zshrc). Non-sensitive values come from
#  prod.auto.tfvars.
# =============================================================================

# ----- Credentials (from Keychain via TF_VAR_*) -----------------------------

variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type        = string
  sensitive   = true
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token (scoped: Zone:Read + DNS:Edit on the iyziops zone)"
  type        = string
  sensitive   = true
}

variable "github_ssh_deploy_key_private" {
  description = "Private half of the GitHub deploy key used by ArgoCD to clone the platform repo"
  type        = string
  sensitive   = true
}

variable "argocd_admin_password_bcrypt" {
  description = "bcrypt hash of the ArgoCD admin password"
  type        = string
  sensitive   = true
}

variable "letsencrypt_email" {
  description = "Email address used for Let's Encrypt account registration"
  type        = string
}

# ----- Environment identity -------------------------------------------------

variable "cluster_name" {
  description = "Cluster identifier used as resource name prefix"
  type        = string
}

variable "environment" {
  description = "Environment label — must be prod"
  type        = string

  validation {
    condition     = var.environment == "prod"
    error_message = "environment must be prod (single-env model)."
  }
}

# ----- Hetzner --------------------------------------------------------------

variable "location_primary" {
  description = "Hetzner datacenter for masters / LBs / NAT box (e.g. fsn1)"
  type        = string
}

variable "worker_location" {
  description = "Hetzner datacenter for worker nodes — must differ from location_primary so Hetzner CCM emits two topology.kubernetes.io/zone labels (Haven infraMultiAZ check expects ≥2 zones)."
  type        = string

  validation {
    condition     = contains(["fsn1", "nbg1", "hel1"], var.worker_location)
    error_message = "worker_location must be one of fsn1, nbg1, hel1."
  }
}

variable "network_zone" {
  description = "Hetzner network zone (e.g. eu-central)"
  type        = string
}

variable "network_cidr" {
  description = "Private network CIDR"
  type        = string
}

variable "subnet_cidr" {
  description = "Private subnet CIDR"
  type        = string
}

variable "api_lb_type" {
  description = "Hetzner API LB type (6443). lb11 is sufficient for control-plane traffic."
  type        = string
}

variable "ingress_lb_type" {
  description = "Hetzner ingress LB type (80/443). lb11 dev, lb21+ for customer-facing prod."
  type        = string
}

variable "operator_cidrs" {
  description = "Allow-list CIDRs for SSH (22) on the NAT bastion. Each entry must be /16 or tighter (/0-/15 rejected so nobody can bypass the no-0.0.0.0/0 rule by splitting the IPv4 space into /1 blocks)."
  type        = list(string)

  validation {
    condition     = !contains(var.operator_cidrs, "0.0.0.0/0") && !contains(var.operator_cidrs, "::/0")
    error_message = "operator_cidrs must not contain 0.0.0.0/0 or ::/0."
  }

  validation {
    condition = alltrue([
      for c in var.operator_cidrs :
      tonumber(split("/", c)[1]) >= 16
    ])
    error_message = "operator_cidrs entries must each be /16 or tighter — no /0-/15 wildcards."
  }
}
