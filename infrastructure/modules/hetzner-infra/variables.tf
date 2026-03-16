variable "environment" {
  type = string
}

variable "location_primary" {
  type    = string
  default = "fsn1"
}

variable "location_secondary" {
  type    = string
  default = "nbg1"
}

variable "management_server_type" {
  type    = string
  default = "cpx32"
}

variable "ssh_public_key" {
  type    = string
  default = "~/.ssh/id_rsa.pub"
}

variable "network_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "subnet_cidr" {
  type    = string
  default = "10.0.1.0/24"
}

variable "os_image" {
  description = "Hetzner OS image (Ubuntu 22.04 - RKE2 compatible)"
  type        = string
  default     = "ubuntu-22.04"
}

variable "rancher_bootstrap_password" {
  description = "Known bootstrap password for Rancher initial login"
  type        = string
  default     = "admin"
}

variable "rancher_version" {
  description = "Rancher server version (for reference)"
  type        = string
  default     = "v2.9.3"
}

variable "rancher_chart_version" {
  description = "Rancher Helm chart version (from rancher-stable repo)"
  type        = string
  default     = "2.9.3"
}

variable "k3s_version" {
  description = "K3s version for management node"
  type        = string
  default     = "v1.30.6+k3s1"
}

variable "cert_manager_version" {
  description = "cert-manager version for management node (Rancher dependency)"
  type        = string
  default     = "v1.16.2"
}
