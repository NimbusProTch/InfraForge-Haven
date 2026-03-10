# ===== Hetzner =====
variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "location_primary" {
  description = "Primary datacenter (Multi-AZ - Haven Check 1)"
  type        = string
  default     = "nbg1" # Nuremberg
}

variable "location_secondary" {
  description = "Secondary datacenter (Multi-AZ - Haven Check 1)"
  type        = string
  default     = "hel1" # Helsinki
}

# Management node (Rancher server)
variable "management_server_type" {
  description = "Rancher management node VM type"
  type        = string
  default     = "cpx32" # 4 vCPU, 8GB RAM (AMD)
}

# Cluster nodes
variable "master_server_type" {
  description = "RKE2 master node VM type"
  type        = string
  default     = "cpx32" # 4 vCPU, 8GB RAM (AMD)
}

variable "worker_server_type" {
  description = "RKE2 worker node VM type"
  type        = string
  default     = "cpx42" # 8 vCPU, 16GB RAM (AMD)
}

variable "master_count" {
  description = "Number of master nodes (Haven Check 2: min 3)"
  type        = number
  default     = 3
}

variable "worker_count" {
  description = "Number of worker nodes (Haven Check 2: min 3)"
  type        = number
  default     = 3
}

variable "ssh_public_key" {
  description = "Path to SSH public key file"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

# ===== Network =====
variable "network_cidr" {
  description = "Private network CIDR"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "Subnet CIDR"
  type        = string
  default     = "10.0.1.0/24"
}

# ===== Rancher =====
variable "rancher_admin_password" {
  description = "Rancher admin password (set in terraform.tfvars)"
  type        = string
  sensitive   = true
}

variable "rancher_bootstrap_password" {
  description = "Known bootstrap password for initial Rancher login"
  type        = string
  default     = "admin"
}

variable "rancher_version" {
  description = "Rancher Docker image tag"
  type        = string
  default     = "v2.9.3"
}

variable "cluster_name" {
  description = "RKE2 cluster name"
  type        = string
  default     = "haven-dev"
}

variable "kubernetes_version" {
  description = "RKE2 Kubernetes version"
  type        = string
  default     = "v1.30.6+rke2r1"
}

variable "os_image" {
  description = "Hetzner OS image (Ubuntu 22.04 - RKE2 compatible)"
  type        = string
  default     = "ubuntu-22.04"
}

# ===== Cloudflare =====
variable "cloudflare_api_token" {
  description = "Cloudflare API token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "domain" {
  description = "Platform domain"
  type        = string
  default     = "haven.dev"
}
