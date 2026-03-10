provider "hcloud" {
  token = var.hcloud_token
}

# Bootstrap provider: first-time Rancher login with known password
provider "rancher2" {
  alias     = "bootstrap"
  api_url   = "https://${module.hetzner_infra.management_ip}"
  insecure  = true
  bootstrap = true
}

# Admin provider: uses token from bootstrap for cluster operations
provider "rancher2" {
  alias     = "admin"
  api_url   = rancher2_bootstrap.admin.url
  token_key = rancher2_bootstrap.admin.token
  insecure  = true
}
