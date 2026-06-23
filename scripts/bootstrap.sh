#!/usr/bin/env bash
# scripts/bootstrap.sh — post-`tofu apply` platform bootstrap (demo-ready)
#
# Runs the manual, data-plane steps that `tofu apply` + ArgoCD cannot do on a
# fresh cluster. Idempotent: safe to re-run. Requires KUBECONFIG pointed at the
# fresh cluster (see `make kubeconfig`).
#
# STATUS (2026-06-23): the VAULT section below is PROVEN live end-to-end —
# ClusterSecretStore vault-backend → Valid/Ready, ExternalSecret → SecretSynced,
# iyziops-api-secrets K8s Secret → 9 keys. The IMAGES / KEYCLOAK / DB / LB_IP
# sections are STUBS pending the app-layer reproducibility work (see
# docs/findings/bringup-reproducibility-2026-06-23.md). Do NOT claim demo-ready
# until those are implemented and live-verified.
set -euo pipefail

: "${KUBECONFIG:?set KUBECONFIG to the fresh cluster (make kubeconfig)}"
VNS=vault-system

log() { printf '\n=== %s ===\n' "$1"; }

# ---------------------------------------------------------------------------
# 1. VAULT — init, unseal, configure, seed.  [PROVEN 2026-06-23]
# ---------------------------------------------------------------------------
bootstrap_vault() {
  log "Vault: fix liveness probe (sealed Vault must not be killed → no crashloop)"
  # The platform-helm Vault values ship a liveness probe WITHOUT sealedcode, so a
  # sealed pod (the state after every restart, no auto-unseal) fails liveness and
  # CrashLoopBackOffs. Tolerate sealed. PERMANENT FIX belongs in platform-helm.yaml
  # vault values (server.livenessProbe.path += &sealedcode=204&uninitcode=204);
  # this patch is the runtime stopgap (ArgoCD auto-sync on the vault app should be
  # disabled or the value fixed in git, else selfHeal reverts it).
  kubectl patch application vault -n argocd --type merge \
    -p '{"spec":{"syncPolicy":{"automated":null}}}' >/dev/null 2>&1 || true
  kubectl patch statefulset vault -n "$VNS" --type json -p \
    '[{"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/v1/sys/health?standbyok=true&sealedcode=204&uninitcode=204"}]' >/dev/null 2>&1 || true

  log "Vault: init (1-of-1 shamir) if needed, store keys in vault-init Secret"
  if ! kubectl get secret vault-init -n "$VNS" >/dev/null 2>&1; then
    local init unseal root
    init=$(kubectl exec -n "$VNS" vault-0 -- vault operator init -key-shares=1 -key-threshold=1 -format=json)
    unseal=$(echo "$init" | python3 -c "import sys,json;print(json.load(sys.stdin)['unseal_keys_b64'][0])")
    root=$(echo "$init" | python3 -c "import sys,json;print(json.load(sys.stdin)['root_token'])")
    kubectl create secret generic vault-init -n "$VNS" \
      --from-literal=unseal_key="$unseal" --from-literal=root_token="$root"
  fi
  local UNSEAL ROOT
  UNSEAL=$(kubectl get secret vault-init -n "$VNS" -o jsonpath='{.data.unseal_key}' | base64 -d)
  ROOT=$(kubectl get secret vault-init -n "$VNS" -o jsonpath='{.data.root_token}' | base64 -d)

  log "Vault: unseal (idempotent — also the auto-unseal-on-restart action)"
  kubectl exec -n "$VNS" vault-0 -- vault operator unseal "$UNSEAL" >/dev/null 2>&1 || true

  log "Vault: configure kv-v2 + kubernetes auth + platform-eso-read policy + ESO role"
  kubectl exec -n "$VNS" vault-0 -- sh -c "
    export VAULT_TOKEN='$ROOT'
    vault secrets enable -path=kv -version=2 kv 2>/dev/null || true
    vault auth enable kubernetes 2>/dev/null || true
    vault write auth/kubernetes/config kubernetes_host=https://kubernetes.default.svc >/dev/null
    printf 'path \"kv/data/platform/*\" { capabilities = [\"read\"] }\npath \"kv/metadata/platform/*\" { capabilities = [\"list\",\"read\"] }\n' | vault policy write platform-eso-read -
    vault write auth/kubernetes/role/external-secrets bound_service_account_names=external-secrets bound_service_account_namespaces=external-secrets policies=platform-eso-read ttl=1h audience=vault >/dev/null
  "

  log "Vault: seed kv/platform/iyziops-api/* (generate where possible; TODO real values)"
  local SK WH
  SK=$(openssl rand -hex 32); WH=$(openssl rand -hex 16)
  kubectl exec -n "$VNS" vault-0 -- sh -c "
    export VAULT_TOKEN='$ROOT'
    vault kv put kv/platform/iyziops-api/session-secret value='$SK' >/dev/null
    vault kv put kv/platform/iyziops-api/webhook-secret value='$WH' >/dev/null
    vault kv put kv/platform/iyziops-api/github-repo-oauth client_secret='${GITHUB_CLIENT_SECRET:-demo-not-wired}' >/dev/null
    vault kv put kv/platform/iyziops-api/database url='${DATABASE_URL:-postgresql+asyncpg://haven:havenpw@iyziops-db.haven-system.svc:5432/haven}' >/dev/null
  "

  log "K8s: pre-create iyziops-api-secrets with the 5 plaintext fields (ESO Merge needs the Secret to pre-exist)"
  kubectl create secret generic iyziops-api-secrets -n haven-system \
    --from-literal=EVEREST_ADMIN_PASSWORD="${EVEREST_ADMIN_PASSWORD:-$(openssl rand -hex 12)}" \
    --from-literal=GITEA_ADMIN_TOKEN="${GITEA_ADMIN_TOKEN:-demo-not-wired}" \
    --from-literal=GITHUB_CLIENT_ID="${GITHUB_CLIENT_ID:-demo-not-wired}" \
    --from-literal=HARBOR_ADMIN_PASSWORD="${HARBOR_ADMIN_PASSWORD:-$(openssl rand -hex 12)}" \
    --from-literal=KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-$(openssl rand -hex 12)}" \
    2>/dev/null || true

  log "ESO: force re-validate store + reconcile, then assert sync"
  kubectl annotate clustersecretstore vault-backend reconcile.external-secrets.io/requested-at="$(date +%s)" --overwrite >/dev/null 2>&1 || true
  kubectl rollout restart deploy/external-secrets -n external-secrets >/dev/null 2>&1 || true
  sleep 25
  kubectl get clustersecretstore vault-backend
  kubectl get externalsecret iyziops-api-secrets-vault -n haven-system
}

# ---------------------------------------------------------------------------
# 2. IMAGES — build iyziops-api/ui, push to fresh Harbor, reconcile digests. [STUB]
# 3. KEYCLOAK — import keycloak/haven-realm.json (Job). [STUB]
# 4. PLATFORM DB — deploy iyziops-db / CNPG, set DATABASE_URL. [STUB]
# 5. LB_IP — patch iyziops-api/ui ConfigMap with `tofu output load_balancer_ingress_ipv4`
#            (+ ArgoCD ignoreDifferences so selfHeal doesn't revert). [STUB]
# These are blocked on app-layer reproducibility work — see
# docs/findings/bringup-reproducibility-2026-06-23.md. Implement in git, not by
# hand-hacking the live cluster.
# ---------------------------------------------------------------------------

bootstrap_vault
log "bootstrap: VAULT done (PROVEN). IMAGES/KEYCLOAK/DB/LB_IP still STUB — not demo-ready yet."
