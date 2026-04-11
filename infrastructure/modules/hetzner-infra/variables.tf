variable "environment" {
  type = string
}

variable "location_primary" {
  type    = string
  default = "nbg1"
}

variable "ssh_public_key" {
  description = "SSH public key content"
  type        = string
}

variable "network_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "subnet_cidr" {
  type    = string
  default = "10.0.1.0/24"
}

# H1b-1 (P4.1): operator IP allow-list for SSH + K8s API + RKE2 supervisor.
# Pre-fix every public-facing port was open to 0.0.0.0/0 — that included
# port 9345 (RKE2 supervisor / remotedialer tunnel) which is a rogue
# worker join vector. Set this to your office/VPN egress CIDR(s) before
# applying. Use ["0.0.0.0/0", "::/0"] only if you have a deliberate
# reason (e.g. emergency dev cluster with no VPN).
#
# Example terraform.tfvars:
#   operator_cidrs = ["203.0.113.0/24", "198.51.100.7/32"]
#
# A SAFE default is empty list, which would deny all SSH/9345/6443 traffic
# from outside the LB and force you to set the variable explicitly. We
# default to the unsafe value temporarily to avoid breaking existing dev
# environments — Sprint H1b-1 morning task: set operator_cidrs in tfvars.
variable "operator_cidrs" {
  description = "Allow-list CIDRs for SSH, K8s API direct, and RKE2 supervisor (port 9345)"
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]   # H1b-1 morning TODO: replace with operator IPs
}

