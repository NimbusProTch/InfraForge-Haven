#cloud-config
package_update: true
packages:
  - curl
  - jq
  - open-iscsi  # Required for Longhorn

write_files:
  # RKE2 server config — written as a script to avoid YAML indentation issues
  - path: /usr/local/bin/write-rke2-config.sh
    permissions: "0755"
    content: |
      #!/bin/bash
      PRIVATE_IP="$1"
      PUBLIC_IP="$2"
      mkdir -p /etc/rancher/rke2
      cat > /etc/rancher/rke2/config.yaml << RKEEOF
      token: "${cluster_token}"
      ${ is_first_master ? "cluster-init: true" : "server: \"https://${first_master_private_ip}:9345\"" }
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
      RKEEOF
      # Fix indentation (remove leading spaces from heredoc)
      sed -i 's/^      //' /etc/rancher/rke2/config.yaml

  # Cilium HelmChartConfig (RKE2 built-in Helm controller)
  - path: /var/lib/rancher/rke2/server/manifests/rke2-cilium-config.yaml
    permissions: "0600"
    content: |
      apiVersion: helm.cattle.io/v1
      kind: HelmChartConfig
      metadata:
        name: rke2-cilium
        namespace: kube-system
      spec:
        valuesContent: |-
          kubeProxyReplacement: true
          k8sServiceHost: "__PRIVATE_IP__"
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
  # Hetzner private network interface name varies (enp7s0, ens10, etc.)
  # Detect by finding the 10.0.x.x IP on any interface
  - |
    PRIVATE_IP=""
    for i in $(seq 1 60); do
      PRIVATE_IP=$(ip -4 addr show | grep -oP '(?<=inet\s)10\.\d+\.\d+\.\d+' | head -1 || echo "")
      if [ -n "$PRIVATE_IP" ]; then break; fi
      sleep 5
    done
    if [ -z "$PRIVATE_IP" ]; then
      # Fallback: Hetzner metadata API
      PRIVATE_IP=$(curl -sf http://169.254.169.254/hetzner/v1/metadata/private-networks 2>/dev/null | grep -oP 'ip-address: \K[\d.]+' | head -1 || echo "")
    fi
    if [ -z "$PRIVATE_IP" ]; then
      echo "ERROR: Could not detect private IP after 300s" >&2
      exit 1
    fi
    PUBLIC_IP=$(curl -sf http://169.254.169.254/hetzner/v1/metadata/public-ipv4 || hostname -I | awk '{print $1}')

    # Write RKE2 config with detected IPs
    /usr/local/bin/write-rke2-config.sh "$PRIVATE_IP" "$PUBLIC_IP"

    # Write Cilium config with detected IPs
    sed -i "s/__PRIVATE_IP__/$PRIVATE_IP/g" /var/lib/rancher/rke2/server/manifests/rke2-cilium-config.yaml

  # Install RKE2 server
  - |
    curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION="${kubernetes_version}" sh -
    systemctl enable rke2-server.service
    systemctl start rke2-server.service

  # Wait for RKE2 to be ready
  - |
    export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
    export PATH=$PATH:/var/lib/rancher/rke2/bin
    for i in $(seq 1 120); do
      if kubectl get nodes >/dev/null 2>&1; then
        echo "RKE2 API ready"
        break
      fi
      sleep 5
    done
