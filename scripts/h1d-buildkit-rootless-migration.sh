#!/bin/bash
# H1d BuildKit rootless cutover helper.
#
# READ THIS FIRST:
#   This script PRINTS the cutover commands and pre-flight checks. It does
#   NOT run the actual `kubectl apply` of the rootless manifest, because:
#     - Mid-tenant-build cutover bricks every active build job
#     - Rootless BuildKit may have unexpected compat issues with our
#       existing tenant Dockerfiles (privileged-only ops, kernel modules)
#     - Rolling back is fast (~10s) but only if the operator is watching
#
# Usage:
#   ./scripts/h1d-buildkit-rootless-migration.sh           # dry-run, prints commands
#   ./scripts/h1d-buildkit-rootless-migration.sh --apply   # NOT YET IMPLEMENTED — manual is intentional

set -euo pipefail

KC="${KUBECONFIG:-infrastructure/environments/dev/kubeconfig}"
NAMESPACE="haven-builds"
DEPLOYMENT="buildkitd"
BASELINE_FILE="platform/manifests/haven-builds/buildkitd.yaml"
ROOTLESS_FILE="platform/manifests/haven-builds-rootless-migration/buildkitd-rootless.yaml"

if [[ "${1:-}" == "--apply" ]]; then
  echo "ERROR: --apply mode is intentionally not implemented." >&2
  echo "       Manual cutover is required so you can rollback fast if rootless breaks." >&2
  exit 1
fi

echo "===== Pre-flight check 1: current buildkitd state ====="
echo "  kubectl --kubeconfig=$KC -n $NAMESPACE get deployment $DEPLOYMENT"
echo "  Expected: 1/1 READY, AGE > 0"
echo ""

echo "===== Pre-flight check 2: no active build jobs ====="
echo "  kubectl --kubeconfig=$KC -n $NAMESPACE get pods -l app!=buildkitd"
echo "  Expected: no buildctl-* pods (or all Completed)"
echo ""
echo "  ALSO check the haven-api build queue:"
echo "  kubectl --kubeconfig=$KC -n haven-system logs deploy/haven-api --tail=50 | grep -i 'build queue'"
echo "  Expected: queue depth 0 or pending only"
echo ""

echo "===== Pre-flight check 3: capture current pod for rollback reference ====="
echo "  kubectl --kubeconfig=$KC -n $NAMESPACE get deployment $DEPLOYMENT -o yaml > /tmp/buildkitd-baseline.yaml"
echo "  (this is your safety net — if cutover fails, kubectl apply -f /tmp/buildkitd-baseline.yaml restores the live state)"
echo ""

echo "===== Pre-flight check 4: RESET cache PVC (CRITICAL for ownership) ====="
echo ""
echo "  ⚠️  The current buildkitd-cache PVC is owned by uid 0 (root) because"
echo "  ⚠️  the privileged container ran as root. The rootless container will"
echo "  ⚠️  run as uid 1000 and will hit EACCES on first cache write. Pod-level"
echo "  ⚠️  fsGroup does NOT reliably retro-chown Longhorn PVC content. The"
echo "  ⚠️  only safe path is to delete + recreate the PVC (cache is rebuildable)."
echo ""
echo "  Cost of reset: first build after cutover takes ~3-5 min (cold cache)"
echo "                 instead of ~30s (warm cache). All subsequent builds are"
echo "                 fast again. Worth it for clean ownership."
echo ""
echo "  Step 4a — scale buildkitd to 0 so the PVC unmounts:"
echo "    kubectl --kubeconfig=$KC -n $NAMESPACE scale deployment $DEPLOYMENT --replicas=0"
echo "    kubectl --kubeconfig=$KC -n $NAMESPACE wait --for=delete pod -l app=buildkitd --timeout=60s"
echo ""
echo "  Step 4b — delete the PVC (safe because no pod is mounting it now):"
echo "    kubectl --kubeconfig=$KC -n $NAMESPACE delete pvc buildkitd-cache"
echo ""
echo "  Step 4c — recreate the PVC from the drift control file:"
echo "    kubectl --kubeconfig=$KC apply -f $BASELINE_FILE"
echo "    # (This re-applies the drift-control file which contains the PVC,"
echo "    #  Service, and Deployment. The Deployment.replicas=0 from step 4a is"
echo "    #  preserved by the apply because we're about to override the spec"
echo "    #  in Step 1 anyway. The PVC is recreated empty.)"
echo ""
echo "  Step 4d — verify PVC is Bound and empty:"
echo "    kubectl --kubeconfig=$KC -n $NAMESPACE get pvc buildkitd-cache"
echo "    # Expected: STATUS=Bound, AGE < 1m"
echo ""

echo "===== Step 1: apply the rootless deployment ====="
echo "  kubectl --kubeconfig=$KC apply -f $ROOTLESS_FILE"
echo ""
echo "  ⚠️  This replaces the live Deployment spec. Old pod terminates, new pod starts."
echo "  ⚠️  ~10-30s window where BuildKit is unavailable."
echo ""

echo "===== Step 2: watch the new pod come up ====="
echo "  kubectl --kubeconfig=$KC -n $NAMESPACE get pods --watch"
echo ""
echo "  Look for: buildkitd-XXXX  1/1  Running  (within ~60s)"
echo ""
echo "  If the new pod stays Pending or CrashLoopBackOff:"
echo "    kubectl --kubeconfig=$KC -n $NAMESPACE describe pod buildkitd-XXXX"
echo "    kubectl --kubeconfig=$KC -n $NAMESPACE logs buildkitd-XXXX --tail=50"
echo ""

echo "===== Step 3: smoke test ====="
echo "  # 3a. Verify the daemon answers — necessary but NOT sufficient"
echo "  kubectl --kubeconfig=$KC -n $NAMESPACE exec deploy/$DEPLOYMENT -- buildctl debug workers"
echo "  # Expected: a worker entry, no permission errors"
echo ""
echo "  # 3b. ACTUAL ROOTLESS BUILD TEST (this proves cache write + userns setup)"
echo "  #     The 'buildctl debug workers' check above only proves the daemon"
echo "  #     socket is up — it would PASS even if the cache dir is unwritable"
echo "  #     or unprivileged-userns clone() is silently broken. We need a real"
echo "  #     build that exercises both."
echo "  kubectl --kubeconfig=$KC -n $NAMESPACE exec deploy/$DEPLOYMENT -- sh -c '"
echo "    mkdir -p /tmp/smoke && \\"
echo "    cd /tmp/smoke && \\"
echo "    printf \"FROM alpine:3.20\\\\nRUN echo rootless-ok > /tmp/marker\\\\n\" > Dockerfile && \\"
echo "    buildctl build --frontend dockerfile.v0 --local context=. --local dockerfile=. 2>&1 | tail -20"
echo "  '"
echo "  # Expected: 'DONE' line, no EACCES, no 'failed to create unprivileged user namespace'"
echo "  # If this fails: the rootless cutover is broken, ROLLBACK immediately."
echo ""
echo "  # 3c. Trigger an actual tenant build via the API"
echo "  TOKEN=\$(curl -s -X POST 'https://keycloak.46.225.42.2.sslip.io/realms/haven/protocol/openid-connect/token' \\"
echo "    -d 'client_id=haven-ui' -d 'client_secret=haven-ui-secret' \\"
echo "    -d 'grant_type=password' -d 'username=admin' -d 'password=HavenAdmin2026!' | jq -r .access_token)"
echo ""
echo "  curl -X POST -H \"Authorization: Bearer \$TOKEN\" \\"
echo "    https://api.46.225.42.2.sslip.io/api/v1/apps/{some-test-app-slug}/build"
echo ""
echo "  # 3d. Watch the build job logs"
echo "  kubectl --kubeconfig=$KC -n $NAMESPACE logs -l job-name=<build-job-name> --tail=100 -f"
echo ""

echo "===== Step 4: verify image landed in Harbor ====="
echo "  curl -s https://harbor.46.225.42.2.sslip.io/v2/library/tenant-{slug}/{app}/tags/list"
echo "  # Expected: a new tag (commit SHA) listed"
echo ""

echo "===== Rollback (if anything is wrong) ====="
echo "  kubectl --kubeconfig=$KC apply -f $BASELINE_FILE"
echo "  # OR (if the baseline file has drifted from live state):"
echo "  kubectl --kubeconfig=$KC apply -f /tmp/buildkitd-baseline.yaml"
echo ""
echo "  Old privileged pod returns within ~10s. Tenant builds resume."
echo ""

echo "===== Cleanup (after successful cutover, after 24h soak) ====="
echo "  rm -f /tmp/buildkitd-baseline.yaml"
echo ""
echo "DONE. Read CAREFULLY before running anything. The pre-flight checks"
echo "matter — mid-build cutover is the failure mode you want to avoid."
