#cloud-config
package_update: true
packages:
  - curl
  - jq
  - open-iscsi  # Required for Longhorn

write_files:
  # RKE2 agent config script
  - path: /usr/local/bin/write-rke2-config.sh
    permissions: "0755"
    content: |
      #!/bin/bash
      PRIVATE_IP="$1"
      PUBLIC_IP="$2"
      mkdir -p /etc/rancher/rke2
      cat > /etc/rancher/rke2/config.yaml << RKEEOF
      token: "${cluster_token}"
      server: "https://${first_master_private_ip}:9345"
      node-ip: "$PRIVATE_IP"
      node-external-ip: "$PUBLIC_IP"
      ${ enable_cis_profile ? "profile: cis\nprotect-kernel-defaults: true" : "" }
      RKEEOF
      sed -i 's/^      //' /etc/rancher/rke2/config.yaml

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

  # Detect private and public IPs (interface name varies on Hetzner)
  - |
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
      echo "ERROR: Could not detect private IP after 300s" >&2
      exit 1
    fi
    PUBLIC_IP=$(curl -sf http://169.254.169.254/hetzner/v1/metadata/public-ipv4 || hostname -I | awk '{print $1}')

    # Write RKE2 config with detected IPs
    /usr/local/bin/write-rke2-config.sh "$PRIVATE_IP" "$PUBLIC_IP"

  # Install RKE2 agent
  - |
    curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" INSTALL_RKE2_VERSION="${kubernetes_version}" sh -
    systemctl enable rke2-agent.service
    systemctl start rke2-agent.service
