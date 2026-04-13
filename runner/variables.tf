# =============================================================================
#  iyziops CI runner — variables
# =============================================================================
#  Tokens come from Keychain via TF_VAR_* (iyziops-env shell function):
#    TF_VAR_hcloud_token          → hetzner-cloud-token
#    TF_VAR_github_runner_token   → github-runner-token
# =============================================================================

# ----- Credentials (sensitive, from Keychain) -------------------------------

variable "hcloud_token" {
  description = "Hetzner Cloud API token (same token used by the platform env)"
  type        = string
  sensitive   = true
}

variable "github_runner_token" {
  description = "GitHub Actions runner registration token — single-use, expires in ~1h if unused"
  type        = string
  sensitive   = true
}

# ----- Identity -------------------------------------------------------------

variable "name" {
  description = "Runner instance name (used as Hetzner server name + SSH key label)"
  type        = string
  default     = "iyziops-ci-runner"
}

variable "github_repo" {
  description = "GitHub owner/repo the runners register against"
  type        = string
}

# ----- Placement ------------------------------------------------------------

variable "location" {
  description = "Hetzner datacenter code (e.g. fsn1, nbg1)"
  type        = string
}

variable "server_type" {
  description = "Hetzner server type (e.g. cx23, cpx21)"
  type        = string
}

variable "os_image" {
  description = "Hetzner OS image"
  type        = string
  default     = "ubuntu-24.04"
}

variable "runner_count" {
  description = "Number of parallel runner instances (systemd units) on this single VM"
  type        = number
  default     = 3

  validation {
    condition     = var.runner_count >= 1 && var.runner_count <= 10
    error_message = "runner_count must be between 1 and 10."
  }
}

variable "runner_labels" {
  description = "GitHub Actions labels applied to every runner instance"
  type        = list(string)
  default     = ["self-hosted", "iyziops"]
}

variable "runner_version" {
  description = "GitHub Actions runner release tag"
  type        = string
  default     = "2.321.0"
}
