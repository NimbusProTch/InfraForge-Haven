# H1b-2 (P4.2): remote tofu state backend (PLACEHOLDER — currently commented out).
#
# Pre-fix this file did not exist. The dev cluster ran on local
# `terraform.tfstate`, which means losing the operator's machine = losing
# the cluster (no drift detection, no multi-operator coordination, no DR).
#
# This file ships a Cloudflare R2 backend block as a recommended starting
# point. R2 has a free 10 GB tier that is plenty for tofu state, lives
# off-Hetzner (real DR isolation from the cluster), and uses standard
# S3 protocol so OpenTofu's `s3` backend works out of the box with
# `skip_credentials_validation` for non-AWS endpoints.
#
# It is COMMENTED OUT. The morning operator must:
#
#   1. Sign up for Cloudflare R2 (free tier, no credit card needed)
#   2. Create a bucket: `haven-tfstate-dev` in eu region
#   3. Create an R2 access key + secret key
#   4. Replace `<account>` and `<bucket>` placeholders below
#   5. Uncomment the `terraform { backend "s3" { ... } }` block
#   6. Run `tofu init -migrate-state` to push local state to R2
#   7. Verify with `tofu state list` (should show every resource)
#   8. Delete `terraform.tfstate` and `terraform.tfstate.backup` files
#      from the local filesystem (the migration leaves them as
#      `*.backup` for safety)
#
# Alternative backends (also off-cluster):
#
# - **Hetzner CX22 VPS + standalone MinIO** (€4.49/mo)
# - **Backblaze B2** (free 10 GB tier)
# - **AWS S3** (real S3, ~free at this volume)
#
# DO NOT use the in-cluster MinIO instance for state — that defeats the
# DR purpose (cluster dies → MinIO dies → state lost → unmanageable).

# terraform {
#   backend "s3" {
#     bucket                      = "haven-tfstate-dev"
#     key                         = "dev/terraform.tfstate"
#
#     # Cloudflare R2 endpoint format:
#     #   https://<account-id>.r2.cloudflarestorage.com
#     # Find the account ID in the R2 dashboard.
#     endpoint                    = "https://<account>.r2.cloudflarestorage.com"
#
#     # R2 ignores region, but the s3 backend requires a value.
#     region                      = "auto"
#
#     # Required when targeting non-AWS S3:
#     skip_credentials_validation = true
#     skip_metadata_api_check     = true
#     skip_region_validation      = true
#     use_path_style              = true
#
#     # H1b-2 SECURITY: do NOT commit access keys here. Set them via
#     # AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables
#     # before `tofu init`. Or use a `~/.aws/credentials` profile and
#     # pass `profile = "haven-tfstate"`.
#   }
# }
