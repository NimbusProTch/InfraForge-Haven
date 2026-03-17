provider "hcloud" {
  token = var.hcloud_token
}

# Bootstrap provider: first-time Rancher login with known password
provider "rancher2" {
  alias     = "bootstrap"
  api_url   = "https://${local.rancher_server_dns}"
  insecure  = true
  bootstrap = true
}

# Admin provider: uses token from bootstrap for cluster operations
provider "rancher2" {
  alias     = "admin"
  api_url   = "https://${local.rancher_server_dns}"
  insecure  = true
  token_key = rancher2_bootstrap.admin.token
  timeout   = "600s"
}
