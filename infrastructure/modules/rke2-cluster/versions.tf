# Sprint H1b-1 (P4.1): minimal version pinning for the rke2-cluster module.
#
# Pre-fix this file did not exist — the module relied entirely on the
# calling environment's `versions.tf` for OpenTofu version pinning. That
# works today (the module only renders cloud-init via `templatefile`,
# zero providers consumed) but having a per-module `required_version`
# guards against accidentally being imported from an environment running
# a too-old OpenTofu / Terraform CLI.
#
# This module declares NO `required_providers` block because it instantiates
# zero provider resources — just template files. If a future change adds
# a `null_resource` / `terraform_data` / etc., add the corresponding entry
# here AND in the calling environment's versions.tf.

terraform {
  required_version = ">= 1.6.0"
}
