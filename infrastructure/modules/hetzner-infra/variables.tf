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
