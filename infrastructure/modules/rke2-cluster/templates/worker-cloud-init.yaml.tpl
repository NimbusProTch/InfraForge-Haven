#cloud-config
# =============================================================================
#  iyziops — worker / agent node
# =============================================================================
#  RKE2 agent. Joins via first master private IP:9345. No manifests, no
#  apiserver flags.
# =============================================================================

package_update: true
package_upgrade: false
packages:
  - curl
  - jq
  - open-iscsi
  - wireguard-tools

write_files:
  - path: /etc/sysctl.d/90-rke2.conf
    permissions: '0644'
    content: |
      vm.panic_on_oom=0
      vm.overcommit_memory=1
      kernel.panic=10
      kernel.panic_on_oops=1

  # ---------- RKE2 config template (base64, runtime IPs substituted in runcmd) ----------
  - path: /etc/rancher/rke2/config.yaml.tpl
    permissions: '0600'
    encoding: b64
    content: ${rke2_config_b64}

runcmd:
  - sysctl --system
  - systemctl enable --now iscsid
  - |
    set -eu
    PRIVATE_IP=""
    for i in $(seq 1 60); do
      PRIVATE_IP=$(ip -4 addr show | grep -oP '(?<=inet\s)10\.\d+\.\d+\.\d+' | head -1 || echo "")
      if [ -n "$PRIVATE_IP" ]; then break; fi
      sleep 5
    done
    if [ -z "$PRIVATE_IP" ]; then
      echo "ERROR: could not detect private IP" >&2
      exit 1
    fi
    PUBLIC_IP=$(curl -sf http://169.254.169.254/hetzner/v1/metadata/public-ipv4 || hostname -I | awk '{print $1}')
    sed "s|__PRIVATE_IP__|$PRIVATE_IP|g; s|__PUBLIC_IP__|$PUBLIC_IP|g" \
      /etc/rancher/rke2/config.yaml.tpl > /etc/rancher/rke2/config.yaml
    chmod 0600 /etc/rancher/rke2/config.yaml
  - |
    set -eu
    until curl -skf "https://${first_master_private_ip}:9345/ping" >/dev/null 2>&1; do
      echo "waiting for first master supervisor 9345..."
      sleep 10
    done
  - |
    for i in 1 2 3 4 5; do
      curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION="${kubernetes_version}" INSTALL_RKE2_TYPE=agent sh - && break
      sleep 10
    done
  - systemctl enable --now rke2-agent
