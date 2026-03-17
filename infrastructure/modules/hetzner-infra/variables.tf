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
  description = "SSH public key content (not file path)"
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

variable "os_image" {
  description = "Hetzner OS image (Ubuntu 22.04 - RKE2 compatible)"
  type        = string
  default     = "ubuntu-22.04"
}

