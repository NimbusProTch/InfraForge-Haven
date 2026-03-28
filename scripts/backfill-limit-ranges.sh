#!/usr/bin/env bash
# backfill-limit-ranges.sh — Apply LimitRange + ResourceQuota to existing tenant namespaces
#
# Usage:
#   ./scripts/backfill-limit-ranges.sh [--dry-run] [--kubeconfig PATH]
#
# What it does:
#   1. Lists all namespaces labelled haven.io/managed=true
#   2. For each, applies the LimitRange (50Gi PVC default = dev tier)
#   3. Optionally patches ResourceQuota to add missing fields (pods, services)
#
# Tier detection: reads the haven.io/tier label on the namespace if present,
# falls back to "free". To set the right tier, patch the namespace label first:
#   kubectl label namespace tenant-acme haven.io/tier=standard --overwrite
#
# IMPORTANT: LimitRange changes do NOT affect existing PVCs — only new PVC requests.

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-}"
DRY_RUN=false
KUBECTL_FLAGS=()

# Parse arguments
for arg in "$@"; do
  case $arg in
    --dry-run)
      DRY_RUN=true
      KUBECTL_FLAGS+=("--dry-run=client")
      ;;
    --kubeconfig)
      shift
      KUBECONFIG="$1"
      ;;
    --kubeconfig=*)
      KUBECONFIG="${arg#*=}"
      ;;
  esac
done

if [[ -n "$KUBECONFIG" ]]; then
  export KUBECONFIG
fi

KUBECTL="kubectl"
if $DRY_RUN; then
  echo "[dry-run] No changes will be applied."
fi

# PVC max by tier
pvc_max_for_tier() {
  case "$1" in
    premium|enterprise) echo "1Ti" ;;
    standard|pro)       echo "200Gi" ;;
    *)                  echo "50Gi" ;;
  esac
}

# Pod/PVC/Service counts by tier
quota_for_tier() {
  local tier="$1"
  case "$tier" in
    premium|enterprise) echo "200 100 50" ;;
    standard|pro)       echo "50 20 20" ;;
    dev|starter)        echo "20 5 10" ;;
    *)                  echo "10 3 5" ;;
  esac
}

echo "==> Listing tenant namespaces (haven.io/managed=true)..."
NAMESPACES=$($KUBECTL get namespaces -l haven.io/managed=true -o jsonpath='{.items[*].metadata.name}')

if [[ -z "$NAMESPACES" ]]; then
  echo "No managed tenant namespaces found."
  exit 0
fi

for NS in $NAMESPACES; do
  echo ""
  echo "--> Namespace: $NS"

  # Detect tier from namespace label
  TIER=$($KUBECTL get namespace "$NS" -o jsonpath='{.metadata.labels.haven\.io/tier}' 2>/dev/null || echo "")
  TIER="${TIER:-free}"
  echo "    Tier: $TIER"

  PVC_MAX=$(pvc_max_for_tier "$TIER")
  read -r PODS PVCS SERVICES <<< "$(quota_for_tier "$TIER")"

  # Apply LimitRange
  echo "    Applying LimitRange (PVC max=$PVC_MAX)..."
  $KUBECTL apply "${KUBECTL_FLAGS[@]}" -n "$NS" -f - <<EOF
apiVersion: v1
kind: LimitRange
metadata:
  name: tenant-limits
  namespace: $NS
spec:
  limits:
    - type: Container
      default:
        cpu: "500m"
        memory: "512Mi"
      defaultRequest:
        cpu: "100m"
        memory: "128Mi"
      min:
        cpu: "10m"
        memory: "32Mi"
      max:
        cpu: "4"
        memory: "4Gi"
    - type: PersistentVolumeClaim
      min:
        storage: "1Gi"
      max:
        storage: "$PVC_MAX"
EOF

  # Patch ResourceQuota with tier-based pod/pvc/service counts
  # Get existing CPU/Memory/Storage limits from current quota
  CPU=$($KUBECTL get resourcequota tenant-quota -n "$NS" -o jsonpath='{.spec.hard.limits\.cpu}' 2>/dev/null || echo "16")
  MEM=$($KUBECTL get resourcequota tenant-quota -n "$NS" -o jsonpath='{.spec.hard.limits\.memory}' 2>/dev/null || echo "32Gi")
  STOR=$($KUBECTL get resourcequota tenant-quota -n "$NS" -o jsonpath='{.spec.hard.requests\.storage}' 2>/dev/null || echo "100Gi")

  echo "    Applying ResourceQuota (pods=$PODS, pvcs=$PVCS, services=$SERVICES)..."
  $KUBECTL apply "${KUBECTL_FLAGS[@]}" -n "$NS" -f - <<EOF
apiVersion: v1
kind: ResourceQuota
metadata:
  name: tenant-quota
  namespace: $NS
spec:
  hard:
    requests.cpu: "$CPU"
    limits.cpu: "$CPU"
    requests.memory: "$MEM"
    limits.memory: "$MEM"
    requests.storage: "$STOR"
    pods: "$PODS"
    persistentvolumeclaims: "$PVCS"
    services: "$SERVICES"
EOF

  # Add PSA labels to namespace if not present
  echo "    Ensuring PSA labels on namespace..."
  $KUBECTL label namespace "$NS" \
    pod-security.kubernetes.io/enforce=restricted \
    pod-security.kubernetes.io/enforce-version=latest \
    pod-security.kubernetes.io/warn=restricted \
    pod-security.kubernetes.io/warn-version=latest \
    --overwrite "${KUBECTL_FLAGS[@]}"

  echo "    Done: $NS"
done

echo ""
echo "==> Backfill complete. Namespaces processed: $(echo $NAMESPACES | wc -w | tr -d ' ')"
echo ""
echo "NOTE: To verify LimitRange was applied:"
echo "  kubectl get limitrange tenant-limits -n <namespace> -o yaml"
echo ""
echo "NOTE: LimitRange changes apply to NEW pod/PVC requests only."
echo "      Existing pods and PVCs are not affected."
