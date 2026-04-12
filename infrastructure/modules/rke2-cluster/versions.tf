# =============================================================================
#  iyziops — RKE2 cluster (version pinning)
# =============================================================================
#  This module instantiates no provider resources — it only renders
#  cloud-init templates via `templatefile`. The required_version guard
#  still exists to catch being called from an ancient tofu CLI.
# =============================================================================

terraform {
  required_version = ">= 1.9.0"
}
