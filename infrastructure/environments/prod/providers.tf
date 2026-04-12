# =============================================================================
#  iyziops — prod providers
# =============================================================================
#  Tokens come from Keychain via TF_VAR_* env vars (see iyziops-env in
#  ~/.zshrc).
# =============================================================================

provider "hcloud" {
  token = var.hcloud_token
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
