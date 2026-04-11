# Remote state backend — Hetzner Object Storage (S3-compatible)
#
# Prerequisites (one-time setup):
#   1. Hetzner Cloud Console → Object Storage → Create Bucket
#      - Name: haven-tfstate-dev
#      - Location: eu-central (Falkenstein)
#   2. Generate S3 credentials: Object Storage → Manage Credentials → Generate
#   3. Set env vars before `tofu init`:
#        export AWS_ACCESS_KEY_ID="<hetzner-s3-access-key>"
#        export AWS_SECRET_ACCESS_KEY="<hetzner-s3-secret-key>"
#   4. Run `tofu init -migrate-state` to push local state to Hetzner S3
#   5. Verify: `tofu state list` (should list all resources)
#   6. Delete local terraform.tfstate after successful migration
#
# DO NOT commit S3 credentials. Use environment variables or ~/.aws/credentials.
# DO NOT use the in-cluster MinIO — cluster dies → state lost → unmanageable.

terraform {
  backend "s3" {
    bucket = "haven-tfstate-dev"
    key    = "dev/terraform.tfstate"

    # Hetzner Object Storage endpoint (Falkenstein)
    # https://docs.hetzner.com/storage/object-storage/overview
    endpoints = {
      s3 = "https://fsn1.your-objectstorage.com"
    }

    region = "eu-central"

    # Required for non-AWS S3 endpoints
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    use_path_style              = true
  }
}
