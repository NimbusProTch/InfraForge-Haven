terraform {
  required_version = ">= 1.6.0" # OpenTofu 1.6+

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.49"
    }
    rancher2 = {
      source  = "rancher/rancher2"
      version = "~> 5.0" # Rancher 2.9.x
    }
  }
}
