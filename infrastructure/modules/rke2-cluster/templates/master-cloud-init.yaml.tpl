#!/bin/bash
set -ex

# ============================================================
# RKE2 Master Node Setup (Haven Platform)
# Runs as user-data script on Hetzner Cloud
# ============================================================

# Install dependencies
apt-get update -qq
apt-get install -y -qq curl jq open-iscsi

# CIS profile requires etcd user/group
useradd -r -c "etcd user" -s /sbin/nologin -M etcd 2>/dev/null || true

# Apply kernel params for CIS hardening
cat > /etc/sysctl.d/90-rke2.conf << 'SYSEOF'
vm.panic_on_oom=0
vm.overcommit_memory=1
kernel.panic=10
kernel.panic_on_oops=1
SYSEOF
sysctl --system

# Enable iscsid for Longhorn
systemctl enable --now iscsid

# Detect private and public IPs
PRIVATE_IP=""
for i in $(seq 1 60); do
  PRIVATE_IP=$(ip -4 addr show | grep -oP '(?<=inet\s)10\.\d+\.\d+\.\d+' | head -1 || echo "")
  if [ -n "$PRIVATE_IP" ]; then break; fi
  sleep 5
done
if [ -z "$PRIVATE_IP" ]; then
  PRIVATE_IP=$(curl -sf http://169.254.169.254/hetzner/v1/metadata/private-networks 2>/dev/null | grep -oP 'ip-address: \K[\d.]+' | head -1 || echo "")
fi
if [ -z "$PRIVATE_IP" ]; then
  echo "ERROR: Could not detect private IP" >&2
  exit 1
fi
PUBLIC_IP=$(curl -sf http://169.254.169.254/hetzner/v1/metadata/public-ipv4 || hostname -I | awk '{print $1}')
echo "Detected IPs: private=$PRIVATE_IP public=$PUBLIC_IP"

# Write RKE2 config
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml << RKEEOF
token: "${cluster_token}"
${ is_first_master ? "cluster-init: true" : "server: https://${first_master_private_ip}:9345" }
node-ip: "$PRIVATE_IP"
node-external-ip: "$PUBLIC_IP"
tls-san:
  - "${lb_ip}"
  - "$PRIVATE_IP"
  - "$PUBLIC_IP"
cni: cilium
disable:
  - rke2-ingress-nginx
${ disable_kube_proxy ? "disable-kube-proxy: true" : "" }
${ enable_cis_profile ? "profile: cis\nprotect-kernel-defaults: true" : "" }
write-kubeconfig-mode: "0644"
# H1a-2: Keycloak OIDC integration for kubectl. Pre-fix the dev cluster
# had ZERO --oidc-* flags on kube-apiserver, so tenant admins could not
# use their Keycloak token with `kubectl`. tenant_service.py was creating
# RoleBindings against subjects like `oidc:tenant_{slug}_admin` but
# kube-apiserver had no OIDC verifier so those bindings were inert.
#
# Activates: tenant admin gets a Keycloak token via the `haven-kubectl`
# client, kubectl sends it as a Bearer, kube-apiserver verifies signature
# against Keycloak's JWKS, extracts `preferred_username` (prefixed with
# `oidc:`) and the `groups` claim (also prefixed `oidc:`), and matches
# them against tenant RoleBindings.
#
# IMPORTANT: the keycloak_url here MUST match the issuer the JWT was
# signed with. The realm import (keycloak/haven-realm.json) emits the
# `groups` protocolMapper that fills the claim.
kube-apiserver-arg:
  - "oidc-issuer-url=${keycloak_oidc_issuer_url}"
  - "oidc-client-id=${keycloak_oidc_client_id}"
  - "oidc-username-claim=preferred_username"
  - "oidc-username-prefix=oidc:"
  - "oidc-groups-claim=groups"
  - "oidc-groups-prefix=oidc:"
# H1b-2 (P4.2): etcd snapshot schedule. Pre-fix the cluster had ZERO
# automated backups — total cluster loss = total data loss for every
# tenant + Harbor + Gitea + Keycloak. Snapshots are written to
# /var/lib/rancher/rke2/server/db/snapshots and (if etcd-s3 is enabled
# below) shipped to an off-cluster S3-compatible bucket.
#
# Defaults: daily at 02:00 UTC, keep 30 most recent snapshots locally.
# Override via the cluster module variables.
etcd-snapshot-schedule-cron: "${etcd_snapshot_schedule}"
etcd-snapshot-retention: ${etcd_snapshot_retention}
etcd-snapshot-dir: /var/lib/rancher/rke2/server/db/snapshots
%{ if etcd_s3_enabled ~}
# H1b-2: off-cluster snapshot upload. The S3 endpoint MUST be off the
# Hetzner cluster — uploading to in-cluster MinIO defeats the purpose
# (cluster dies → MinIO dies → snapshots lost). Recommended: Cloudflare
# R2 (free 10 GB tier) or a dedicated VPS-hosted MinIO.
etcd-s3: true
etcd-s3-endpoint: "${etcd_s3_endpoint}"
etcd-s3-bucket: "${etcd_s3_bucket}"
etcd-s3-folder: "${etcd_s3_folder}"
etcd-s3-region: "${etcd_s3_region}"
etcd-s3-access-key: "${etcd_s3_access_key}"
etcd-s3-secret-key: "${etcd_s3_secret_key}"
%{ endif ~}
RKEEOF

# Write Cilium HelmChartConfig
mkdir -p /var/lib/rancher/rke2/server/manifests
cat > /var/lib/rancher/rke2/server/manifests/rke2-cilium-config.yaml << 'CILEOF'
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: rke2-cilium
  namespace: kube-system
spec:
  valuesContent: |-
    kubeProxyReplacement: true
    k8sServiceHost: "__CILIUM_IP__"
    k8sServicePort: "6443"
    operator:
      replicas: ${cilium_operator_replicas}
    gatewayAPI:
      enabled: true
    hubble:
      enabled: ${enable_hubble}
      relay:
        enabled: ${enable_hubble}
      ui:
        enabled: ${enable_hubble}
    ipam:
      mode: "kubernetes"
    tolerations:
      - operator: "Exists"
CILEOF
sed -i "s/__CILIUM_IP__/$PRIVATE_IP/g" /var/lib/rancher/rke2/server/manifests/rke2-cilium-config.yaml

# Install RKE2
curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION="${kubernetes_version}" sh -
systemctl enable rke2-server.service
systemctl start rke2-server.service

# Wait for RKE2 to be ready
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
export PATH=$PATH:/var/lib/rancher/rke2/bin
for i in $(seq 1 120); do
  if kubectl get nodes >/dev/null 2>&1; then
    echo "RKE2 API ready"
    break
  fi
  sleep 5
done

echo "Master setup complete!"
