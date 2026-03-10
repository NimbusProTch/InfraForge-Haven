# ===== Hetzner =====
variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Ortam adı"
  type        = string
  default     = "dev"
}

variable "location_primary" {
  description = "Birincil datacenter (Multi-AZ - Haven Check 1)"
  type        = string
  default     = "fsn1" # Falkenstein
}

variable "location_secondary" {
  description = "İkincil datacenter (Multi-AZ - Haven Check 1)"
  type        = string
  default     = "nbg1" # Nuremberg
}

# Management node (Rancher server)
variable "management_server_type" {
  description = "Rancher management node VM tipi"
  type        = string
  default     = "cx31" # 4 vCPU, 8GB RAM
}

# Cluster nodes
variable "master_server_type" {
  description = "RKE2 master node VM tipi"
  type        = string
  default     = "cx31" # 4 vCPU, 8GB RAM
}

variable "worker_server_type" {
  description = "RKE2 worker node VM tipi"
  type        = string
  default     = "cx41" # 8 vCPU, 16GB RAM
}

variable "master_count" {
  description = "Master node sayısı (Haven Check 2: min 3)"
  type        = number
  default     = 3
}

variable "worker_count" {
  description = "Worker node sayısı (Haven Check 2: min 3)"
  type        = number
  default     = 3
}

variable "ssh_public_key" {
  description = "SSH public key dosya yolu"
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
variable "rancher_api_url" {
  description = "Rancher API URL"
  type        = string
  default     = ""
}

variable "rancher_token_key" {
  description = "Rancher API token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "rancher_insecure" {
  description = "Skip TLS verification (dev only)"
  type        = bool
  default     = true
}

variable "kubernetes_version" {
  description = "RKE2 Kubernetes versiyonu"
  type        = string
  default     = "v1.30.6+rke2r1"
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
