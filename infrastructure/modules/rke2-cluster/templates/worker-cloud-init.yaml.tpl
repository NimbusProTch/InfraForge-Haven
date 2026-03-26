#cloud-config
package_update: true
packages:
  - curl
  - jq
  - open-iscsi  # Required for Longhorn

write_files:
  # RKE2 agent config
  - path: /etc/rancher/rke2/config.yaml
    permissions: "0600"
    content: |
      token: "${cluster_token}"
      server: "https://${first_master_private_ip}:9345"
      node-ip: "__PRIVATE_IP__"
      node-external-ip: "__PUBLIC_IP__"
      %{ if enable_cis_profile ~}
      profile: cis
      protect-kernel-defaults: true
      %{ endif ~}

  # Kernel params for CIS hardening
  - path: /etc/sysctl.d/90-rke2.conf
    permissions: "0644"
    content: |
      vm.panic_on_oom=0
      vm.overcommit_memory=1
      kernel.panic=10
      kernel.panic_on_oops=1

runcmd:
  # Apply kernel params
  - sysctl --system

  # Enable and start iscsid for Longhorn
  - systemctl enable --now iscsid

  # Detect private and public IPs
  - |
    PRIVATE_IP=""
    for i in $(seq 1 30); do
      PRIVATE_IP=$(ip -4 addr show ens10 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "")
      if [ -n "$PRIVATE_IP" ]; then break; fi
      sleep 5
    done
    if [ -z "$PRIVATE_IP" ]; then
      echo "ERROR: Could not detect private IP after 150s" >&2
      exit 1
    fi
    PUBLIC_IP=$(curl -sf http://169.254.169.254/hetzner/v1/metadata/public-ipv4 || hostname -I | awk '{print $1}')

    # Replace placeholders
    sed -i "s/__PRIVATE_IP__/$PRIVATE_IP/g" /etc/rancher/rke2/config.yaml
    sed -i "s/__PUBLIC_IP__/$PUBLIC_IP/g" /etc/rancher/rke2/config.yaml

  # Install RKE2 agent
  - |
    curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" INSTALL_RKE2_VERSION="${kubernetes_version}" sh -
    systemctl enable rke2-agent.service
    systemctl start rke2-agent.service
