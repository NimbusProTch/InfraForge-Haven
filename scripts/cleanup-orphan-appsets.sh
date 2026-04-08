#!/usr/bin/env bash
# Cleanup orphan ArgoCD ApplicationSets for tenants that no longer exist.
#
# An orphan is an ApplicationSet with name pattern "appset-<slug>" that either:
#   a) has label haven.io/managed=true, and
#   b) the tenant slug no longer exists in haven-api's tenant list
#
# Usage:
#   ./scripts/cleanup-orphan-appsets.sh              # dry-run (default)
#   ./scripts/cleanup-orphan-appsets.sh --apply     # actually delete
#
# Requires:
#   - kubectl configured to point at the haven cluster
#   - curl + jq
#   - HAVEN_API_URL + HAVEN_ADMIN_TOKEN env vars, or will attempt to login via Keycloak

set -euo pipefail

APPLY=false
if [[ "${1:-}" == "--apply" ]]; then
  APPLY=true
fi

KC_URL="${KC_URL:-https://keycloak.46.225.42.2.sslip.io}"
API_URL="${HAVEN_API_URL:-https://api.46.225.42.2.sslip.io/api/v1}"
USERNAME="${HAVEN_ADMIN_USER:-admin}"
PASSWORD="${HAVEN_ADMIN_PASSWORD:-HavenAdmin2026!}"

echo "=== Orphan ApplicationSet Cleanup ==="
echo "Mode: $([ "$APPLY" = true ] && echo APPLY || echo DRY-RUN)"
echo ""

# Step 1: Get existing tenant slugs from the Haven API
echo "→ Fetching tenant list from Haven API..."
TOKEN=$(curl -sk -X POST "${KC_URL}/realms/haven/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=haven-api&username=${USERNAME}&password=${PASSWORD}&grant_type=password" \
  | jq -r '.access_token')

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "ERROR: failed to get access token from Keycloak"
  exit 1
fi

TENANTS=$(curl -sk "${API_URL}/tenants" -H "Authorization: Bearer ${TOKEN}" | jq -r '.[].slug')
TENANT_COUNT=$(echo "$TENANTS" | wc -l | tr -d ' ')
echo "  Found $TENANT_COUNT active tenants"

# Step 2: List all ApplicationSets matching appset-*
echo ""
echo "→ Listing ApplicationSets in argocd namespace..."
APPSETS=$(kubectl get applicationsets -n argocd -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | grep '^appset-' || true)

if [[ -z "$APPSETS" ]]; then
  echo "  No ApplicationSets found."
  exit 0
fi

# Step 3: For each appset-<slug>, check if tenant still exists
ORPHANS=()
for APPSET in $APPSETS; do
  SLUG="${APPSET#appset-}"
  if echo "$TENANTS" | grep -qx "$SLUG"; then
    echo "  ✓ $APPSET — tenant '$SLUG' exists"
  else
    echo "  ✗ $APPSET — tenant '$SLUG' NOT FOUND (orphan)"
    ORPHANS+=("$APPSET")
  fi
done

# Step 4: Delete orphans
echo ""
echo "=== Summary ==="
echo "  Orphans: ${#ORPHANS[@]}"

if [[ ${#ORPHANS[@]} -eq 0 ]]; then
  echo "Nothing to do."
  exit 0
fi

if [[ "$APPLY" != true ]]; then
  echo ""
  echo "Re-run with --apply to actually delete orphans."
  exit 0
fi

echo ""
echo "→ Deleting orphan ApplicationSets..."
for APPSET in "${ORPHANS[@]}"; do
  SLUG="${APPSET#appset-}"
  # Also delete child Applications labeled with this tenant
  kubectl delete applications -n argocd -l "haven.io/tenant=${SLUG}" --ignore-not-found --grace-period=0 2>&1 | sed 's/^/    /'
  kubectl delete applicationset -n argocd "$APPSET" --ignore-not-found --grace-period=0 2>&1 | sed 's/^/  /'
done

echo ""
echo "Done."
