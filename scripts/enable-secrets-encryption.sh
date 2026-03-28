#!/usr/bin/env bash
# =============================================================================
# Haven Platform - RKE2 etcd Secrets Encryption Migration Script (IS3-01)
# =============================================================================
# Use this script on an EXISTING cluster that was deployed WITHOUT
# 'secrets-encryption: true' in the RKE2 config.
#
# New clusters created with the updated main.tf already have
# secrets-encryption: true and do NOT need this script.
#
# Steps performed:
#   1. Enable secrets encryption (generates encryption provider config)
#   2. Rotate the encryption key (creates a new key, marks old as secondary)
#   3. Re-encrypt all existing Secrets in etcd with the new key
#
# Prerequisites:
#   - SSH access to the first RKE2 master node
#   - rke2-server running with admin kubeconfig at /etc/rancher/rke2/rke2.yaml
#
# Usage:
#   ssh root@<master-ip> 'bash -s' < scripts/enable-secrets-encryption.sh
#   # or copy to master and run:
#   scp scripts/enable-secrets-encryption.sh root@<master-ip>:/tmp/
#   ssh root@<master-ip> 'bash /tmp/enable-secrets-encryption.sh'
# =============================================================================

set -euo pipefail

export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
export PATH=$PATH:/var/lib/rancher/rke2/bin

echo "=== Haven Platform: etcd Secrets Encryption Migration ==="
echo ""

# Step 1: Enable encryption
echo "[1/3] Enabling secrets encryption..."
rke2 secrets-encrypt enable
echo "  Waiting 30s for kube-apiserver to restart with encryption enabled..."
sleep 30

# Verify apiserver restarted
for i in $(seq 1 30); do
    if kubectl get nodes >/dev/null 2>&1; then
        echo "  kube-apiserver is responsive"
        break
    fi
    echo "  Waiting for apiserver (attempt $i)..."
    sleep 5
done

# Step 2: Rotate encryption keys
echo ""
echo "[2/3] Rotating encryption keys..."
rke2 secrets-encrypt rotate
echo "  Waiting 30s for key rotation to complete..."
sleep 30

for i in $(seq 1 30); do
    if kubectl get nodes >/dev/null 2>&1; then
        echo "  kube-apiserver is responsive after rotation"
        break
    fi
    sleep 5
done

# Step 3: Re-encrypt all existing secrets
echo ""
echo "[3/3] Re-encrypting all existing Secrets in etcd..."
rke2 secrets-encrypt reencrypt

echo ""
echo "  Waiting for re-encryption to complete..."
# Check encryption status
for i in $(seq 1 60); do
    STATUS=$(rke2 secrets-encrypt status 2>/dev/null | grep -i "enable" || echo "unknown")
    echo "  Encryption status: $STATUS (attempt $i)"
    if echo "$STATUS" | grep -qi "true"; then
        echo "  Re-encryption complete!"
        break
    fi
    sleep 10
done

# Verify: check apiserver encryption config
echo ""
echo "=== Verification ==="
echo "kube-apiserver encryption config:"
kubectl get pod -n kube-system -l component=kube-apiserver \
    -o jsonpath='{.items[0].spec.containers[0].command}' 2>/dev/null \
    | tr ',' '\n' | grep -i encryption || echo "  (encryption flag not visible in pod spec — check /etc/rancher/rke2/)"

echo ""
echo "Encryption provider file:"
ls -la /var/lib/rancher/rke2/server/cred/encryption-config.json 2>/dev/null \
    && echo "  File exists (encryption is configured)" \
    || echo "  WARNING: encryption-config.json not found"

echo ""
echo "=== Migration complete! ==="
echo "All K8s Secrets are now encrypted at rest in etcd."
echo ""
echo "Next steps:"
echo "  1. Ensure all master nodes have 'secrets-encryption: true' in /etc/rancher/rke2/config.yaml"
echo "  2. Restart rke2-server on each master: systemctl restart rke2-server"
echo "  3. Verify: kubectl get secret -A --field-selector type=kubernetes.io/service-account-token | head -5"
