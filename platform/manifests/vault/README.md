# Vault + External Secrets Operator

## Architecture

```
Haven API → Vault KV v2 (write sensitive env vars)
    ↓
ESO ClusterSecretStore → reads from Vault
    ↓
ExternalSecret (per app) → syncs to K8s Secret
    ↓
Pod envFrom.secretRef → reads K8s Secret
```

## Prerequisites

1. **Vault** deployed in `vault-system` namespace (Helm: hashicorp/vault)
2. **ESO** deployed in `external-secrets` namespace (Helm: external-secrets/external-secrets)
3. Vault KV v2 engine enabled at `haven/`
4. Vault K8s auth enabled + `haven-eso` role
5. Vault `haven-api-writer` policy + token for Haven API

## Setup Commands

```bash
# Vault (dev mode for dev, HA for prod)
helm install vault hashicorp/vault -n vault-system --set server.dev.enabled=true

# ESO
helm install external-secrets external-secrets/external-secrets -n external-secrets

# Vault config
kubectl exec -n vault-system vault-0 -- vault secrets enable -path=haven kv-v2
kubectl exec -n vault-system vault-0 -- vault auth enable kubernetes
kubectl exec -n vault-system vault-0 -- vault write auth/kubernetes/config kubernetes_host="https://kubernetes.default.svc:443"
kubectl exec -n vault-system vault-0 -- vault policy write haven-eso-reader - <<EOF
path "haven/data/*" { capabilities = ["read"] }
path "haven/metadata/*" { capabilities = ["read", "list"] }
EOF
kubectl exec -n vault-system vault-0 -- vault write auth/kubernetes/role/haven-eso \
  bound_service_account_names=external-secrets \
  bound_service_account_namespaces=external-secrets \
  policies=haven-eso-reader ttl=1h

# ClusterSecretStore
kubectl apply -f platform/manifests/vault/cluster-secret-store.yaml

# Haven API token (set in haven-api-secrets)
VAULT_TOKEN=$(kubectl exec -n vault-system vault-0 -- vault token create -policy=haven-api-writer -period=720h -format=json | jq -r .auth.client_token)
```

## Environment Variables (haven-api-secrets)

```
VAULT_URL=http://vault.vault-system.svc:8200
VAULT_TOKEN=<token from above>
```
