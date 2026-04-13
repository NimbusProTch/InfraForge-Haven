# =============================================================================
#  iyziops — RKE2 cluster (version pinning)
# =============================================================================
#  This module renders cloud-init via `templatefile` and uses the http
#  provider once at plan time to fetch the upstream Gateway API CRD
#  bundle so it can be embedded as a bootstrap manifest. No long-lived
#  resources are created in this module.
# =============================================================================

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
  }
}
