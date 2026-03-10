terraform {
  required_version = ">= 1.6.0" # OpenTofu 1.6+

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.49"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
    rancher2 = {
      source  = "rancher/rancher2"
      version = "~> 5.0" # Rancher 2.9.x
    }
  }
}
