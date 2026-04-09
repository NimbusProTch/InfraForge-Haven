#!/bin/bash
# H1e Vault → ESO migration helper for haven-api-secrets.
#
# READ THIS FIRST:
#   This script READS the existing native K8s Secret values, prints them
#   in a `vault kv put` command format, and then EXITS. It does NOT
#   actually write to Vault, delete the native Secret, or apply the
#   ExternalSecret. Those steps are MANUAL on purpose — losing a key
#   between steps = permanently bricking haven-api.
#
# Prerequisites:
#   - kubectl pointed at the dev cluster (KUBECONFIG=infrastructure/environments/dev/kubeconfig)
#   - Vault CLI installed (`brew install vault` or `apt install vault`)
#   - vault auth login (Vault root token from `kubectl get secret -n vault-system vault-init -o jsonpath='{.data.root_token}' | base64 -d` if you have the bootstrap secret)
#   - VAULT_ADDR set to https://vault.46.225.42.2.sslip.io OR port-forward
#
# Usage:
#   ./scripts/h1e-vault-migrate-haven-api-secrets.sh           # dry-run, prints commands
#   ./scripts/h1e-vault-migrate-haven-api-secrets.sh --apply   # NOT YET IMPLEMENTED — manual is intentional

set -euo pipefail

KC="${KUBECONFIG:-infrastructure/environments/dev/kubeconfig}"
NAMESPACE="haven-system"
SECRET_NAME="haven-api-secrets"
VAULT_PATH="haven/haven-api"

if [[ "${1:-}" == "--apply" ]]; then
  echo "ERROR: --apply mode is intentionally not implemented." >&2
  echo "       Manual cutover is required to avoid bricking haven-api between steps." >&2
  exit 1
fi

echo "===== Step 1: read existing $SECRET_NAME from K8s ====="
kubectl --kubeconfig="$KC" get secret "$SECRET_NAME" -n "$NAMESPACE" -o json \
  | jq -r '.data | to_entries[] | "\(.key)=\(.value | @base64d)"' \
  > /tmp/haven-api-secrets.txt

echo "  ✅ wrote to /tmp/haven-api-secrets.txt ($(wc -l < /tmp/haven-api-secrets.txt) keys)"
echo "  Keys:"
cut -d= -f1 /tmp/haven-api-secrets.txt | sed 's/^/    - /'

echo ""
echo "===== Step 2: vault kv put command (manual run) ====="
echo "Run THIS command (replace VAULT_TOKEN if needed):"
echo ""
{
  echo -n "  vault kv put $VAULT_PATH"
  while IFS='=' read -r key value; do
    # Escape single quotes in value
    escaped="${value//\'/\'\\\'\'}"
    echo -n " \\
    ${key}='${escaped}'"
  done < /tmp/haven-api-secrets.txt
  echo ""
} | tee /tmp/vault-put-command.sh

echo ""
echo "===== Step 3: verify the write ====="
echo "  vault kv get $VAULT_PATH"
echo ""
echo "  Expected output: a JSON dict with all $(wc -l < /tmp/haven-api-secrets.txt) keys."

echo ""
echo "===== Step 4: apply the ExternalSecret manifest ====="
echo "  kubectl --kubeconfig=$KC apply -f platform/manifests/haven-api/externalsecret.yaml"
echo ""
echo "  Wait for ESO to populate (initial reconcile takes ~10s):"
echo "  kubectl --kubeconfig=$KC wait externalsecret/haven-api-secrets-sync -n $NAMESPACE --for=condition=Ready --timeout=60s"
echo ""
echo "  At this point ESO will REFUSE to overwrite the existing native Secret"
echo "  (creationPolicy: Owner — only owns secrets it created)."
echo "  Status will show: 'Conflict: secret exists and is not owned by this ExternalSecret'"

echo ""
echo "===== Step 5: cutover (delete native, ESO recreates) ====="
echo "  # CRITICAL pre-conditions before cutover:"
echo "  #   1. Vault put completed with all 9 keys (verify with vault kv get)"
echo "  #   2. NO HPA scale-up event in progress (otherwise new pod starts"
echo "  #      with envFrom failing during the ~10s gap):"
echo "  #         kubectl --kubeconfig=$KC get hpa -n $NAMESPACE"
echo "  #   3. NO crashloop in progress (same reason):"
echo "  #         kubectl --kubeconfig=$KC get pods -n $NAMESPACE -l app=haven-api"
echo "  #   4. Optionally freeze replicas at current count for ~2 min:"
echo "  #         kubectl --kubeconfig=$KC scale deployment/haven-api -n $NAMESPACE --replicas=2"
echo "  #"
echo "  kubectl --kubeconfig=$KC delete secret $SECRET_NAME -n $NAMESPACE"
echo "  # Within ~10s, ESO recreates the secret from Vault"
echo "  kubectl --kubeconfig=$KC get secret $SECRET_NAME -n $NAMESPACE -o jsonpath='{.metadata.labels}'"
echo "  # Expected: '{\"haven.io/managed-by\":\"external-secrets\",\"haven.io/source\":\"vault\"}'"

echo ""
echo "===== Step 6: restart haven-api to pick up Vault-sourced env ====="
echo "  kubectl --kubeconfig=$KC rollout restart deployment/haven-api -n $NAMESPACE"
echo "  kubectl --kubeconfig=$KC rollout status deployment/haven-api -n $NAMESPACE"

echo ""
echo "===== Step 7: smoke test ====="
echo "  curl -s -o /dev/null -w 'HTTP %{http_code}\n' https://api.46.225.42.2.sslip.io/api/docs"
echo "  # Expected: 200"
echo ""
echo "  # Real auth round-trip:"
echo "  TOKEN=\$(curl -s -X POST 'https://keycloak.46.225.42.2.sslip.io/realms/haven/protocol/openid-connect/token' \\"
echo "    -d 'client_id=haven-ui' -d 'client_secret=haven-ui-secret' \\"
echo "    -d 'grant_type=password' -d 'username=admin' -d 'password=HavenAdmin2026!' \\"
echo "    | jq -r .access_token)"
echo "  curl -s -H \"Authorization: Bearer \$TOKEN\" https://api.46.225.42.2.sslip.io/api/v1/tenants/me"
echo ""
echo "===== Rollback ====="
echo "  # If anything is wrong, recreate the native secret from /tmp/haven-api-secrets.txt:"
echo "  kubectl --kubeconfig=$KC delete externalsecret haven-api-secrets-sync -n $NAMESPACE"
echo "  kubectl --kubeconfig=$KC delete secret $SECRET_NAME -n $NAMESPACE --ignore-not-found"
echo "  kubectl --kubeconfig=$KC create secret generic $SECRET_NAME -n $NAMESPACE \\"
while IFS='=' read -r key value; do
  echo "    --from-literal=$key='$value' \\"
done < /tmp/haven-api-secrets.txt
echo ""
echo "  kubectl --kubeconfig=$KC rollout restart deployment/haven-api -n $NAMESPACE"
echo ""
echo "===== Cleanup ====="
echo "  # SECURE delete (overwrite + remove) — both files contain plaintext secrets:"
echo "  shred -u /tmp/haven-api-secrets.txt /tmp/vault-put-command.sh 2>/dev/null \\"
echo "    || rm -P /tmp/haven-api-secrets.txt /tmp/vault-put-command.sh 2>/dev/null \\"
echo "    || rm -f /tmp/haven-api-secrets.txt /tmp/vault-put-command.sh"
echo "  # (shred is preferred; rm -P is the macOS equivalent; plain rm is the fallback)"
echo ""
echo "DONE. /tmp/haven-api-secrets.txt and /tmp/vault-put-command.sh contain"
echo "plaintext secrets — secure-delete them with the command above when done."
