#cloud-config
# =============================================================================
#  iyziops — worker / agent node
# =============================================================================
#  RKE2 agent. Joins via first master private IP:9345. No manifests, no
#  apiserver flags. No public IPv4 — Haven privatenetworking. bootcmd
#  waits for NAT egress before apt install.
# =============================================================================

# Private-only node bootstrap (see master-cloud-init.yaml.tpl for full note).
bootcmd:
  - |
    mkdir -p /etc/netplan
    cat > /etc/netplan/99-iyziops-private.yaml <<'EOF'
    network:
      version: 2
      ethernets:
        all-en:
          match:
            name: "en*"
          dhcp4: true
          dhcp4-overrides:
            use-routes: true
          routes:
            - to: default
              via: 10.10.0.1
              metric: 100
          nameservers:
            addresses: [185.12.64.1, 185.12.64.2]
    EOF
    chmod 0600 /etc/netplan/99-iyziops-private.yaml
    netplan apply
    for i in $(seq 1 60); do
      ping -W 2 -c 1 1.1.1.1 >/dev/null 2>&1 && break
      sleep 5
    done

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
    sed "s|__PRIVATE_IP__|$PRIVATE_IP|g" \
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
