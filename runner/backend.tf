# =============================================================================
#  iyziops CI runner — remote state backend
# =============================================================================
#  Separate bucket from the platform environments so a runner mistake can
#  never scribble on the prod cluster's state. Credentials come from the
#  same `iyziops-env` shell function that loads the platform env.
# =============================================================================

terraform {
  backend "s3" {
    bucket = "iyziops-tfstate-runner"
    key    = "runner/terraform.tfstate"

    endpoints = {
      s3 = "https://fsn1.your-objectstorage.com"
    }
    region = "fsn1"

    # Enable after upgrading to OpenTofu 1.10+:
    # use_lockfile = true

    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    use_path_style              = true
  }
}
