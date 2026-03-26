#!/bin/bash
set -ex

# ============================================================
# RKE2 Worker Node Setup (Haven Platform)
# Runs as user-data script on Hetzner Cloud
# ============================================================

# Install dependencies
apt-get update -qq
apt-get install -y -qq curl jq open-iscsi

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
server: "https://${first_master_private_ip}:9345"
node-ip: "$PRIVATE_IP"
node-external-ip: "$PUBLIC_IP"
${ enable_cis_profile ? "profile: cis\nprotect-kernel-defaults: true" : "" }
RKEEOF

# Install RKE2 agent
curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" INSTALL_RKE2_VERSION="${kubernetes_version}" sh -
systemctl enable rke2-agent.service
systemctl start rke2-agent.service

echo "Worker setup complete!"
