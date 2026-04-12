# =============================================================================
#  iyziops — prod environment remote state backend
# =============================================================================
#  Hetzner Object Storage is S3-compatible. The bucket iyziops-tfstate-prod
#  must exist in fsn1 with versioning enabled before `tofu init`. Credentials
#  come from the Keychain via the `iyziops-env` shell function
#  (~/.zshrc) which exports AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY.
#
#  Native S3 locking (`use_lockfile = true`) requires OpenTofu 1.10+. On
#  older tofu CLIs remove the line and rely on the single-operator
#  convention — concurrent apply attempts will clobber state.
# =============================================================================

terraform {
  backend "s3" {
    bucket = "iyziops-tfstate-prod"
    key    = "prod/terraform.tfstate"

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
