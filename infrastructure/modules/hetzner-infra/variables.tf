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
  default = "cx31"
}

variable "master_server_type" {
  type    = string
  default = "cx31"
}

variable "worker_server_type" {
  type    = string
  default = "cx41"
}

variable "master_count" {
  type    = number
  default = 3
}

variable "worker_count" {
  type    = number
  default = 3
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
  description = "Hetzner OS image (Ubuntu 22.04 - RKE2 uyumlu)"
  type        = string
  default     = "ubuntu-22.04"
}
