# Production providers — Phase 2+ (Cyso Cloud / Leafcloud Amsterdam).
#
# Skeleton only. Sprint 2 will fill in credentials + actual deploy.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 2.1"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.45"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.16"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.34"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }

  # H1b-2 morning TODO: enable a real remote state backend before any
  # production apply. Recommended: Cloudflare R2 (free 10 GB tier,
  # off-Hetzner = real DR isolation).
  #
  # backend "s3" {
  #   bucket                      = "haven-prod-tfstate"
  #   key                         = "production/terraform.tfstate"
  #   endpoint                    = "https://<account>.r2.cloudflarestorage.com"
  #   region                      = "auto"
  #   skip_credentials_validation = true
  #   skip_metadata_api_check     = true
  #   skip_region_validation      = true
  #   use_path_style              = true
  # }
}
