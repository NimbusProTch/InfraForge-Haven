#cloud-config
# =============================================================================
#  iyziops — additional master node (HA join)
# =============================================================================
#  Joins the cluster via the first master's private IP on port 9345. Does
#  NOT write any Helm Controller manifests — etcd replicates them from the
#  bootstrap master once the new master registers.
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

  - path: /etc/rancher/rke2/audit-policy.yaml
    permissions: '0600'
    content: |
      apiVersion: audit.k8s.io/v1
      kind: Policy
      omitStages:
        - RequestReceived
      rules:
        - level: None
          verbs: ["get", "list", "watch"]
        - level: RequestResponse
          resources:
            - group: "rbac.authorization.k8s.io"
              resources: ["clusterroles", "clusterrolebindings", "roles", "rolebindings"]
        - level: Metadata
          verbs: ["create", "update", "patch", "delete"]

  - path: /etc/rancher/rke2/config.yaml.tpl
    permissions: '0600'
    content: |
      token: "${cluster_token}"
      server: "https://${first_master_private_ip}:9345"
      node-ip: "__PRIVATE_IP__"
      node-external-ip: "__PUBLIC_IP__"
      cni: cilium
      disable:
        - rke2-ingress-nginx
      tls-san:
        - "${lb_ip}"
        - "${lb_private_ip}"
        - "__PRIVATE_IP__"
        - "__PUBLIC_IP__"
      %{ if disable_kube_proxy ~}
      disable-kube-proxy: true
      %{ endif ~}
      %{ if enable_cis_profile ~}
      profile: cis
      protect-kernel-defaults: true
      %{ endif ~}
      write-kubeconfig-mode: "0644"
      kube-apiserver-arg:
        - "oidc-issuer-url=${keycloak_oidc_issuer_url}"
        - "oidc-client-id=${keycloak_oidc_client_id}"
        - "oidc-username-claim=preferred_username"
        - "oidc-username-prefix=oidc:"
        - "oidc-groups-claim=groups"
        - "oidc-groups-prefix=oidc:"
        - "audit-policy-file=/etc/rancher/rke2/audit-policy.yaml"
        - "audit-log-path=/var/log/kube-audit/audit.log"
        - "audit-log-maxage=30"
        - "audit-log-maxbackup=10"
        - "audit-log-maxsize=100"
      etcd-snapshot-schedule-cron: "${etcd_snapshot_schedule}"
      etcd-snapshot-retention: ${etcd_snapshot_retention}
      %{ if etcd_s3_enabled ~}
      etcd-s3: true
      etcd-s3-endpoint: "${etcd_s3_endpoint}"
      etcd-s3-bucket: "${etcd_s3_bucket}"
      etcd-s3-region: "${etcd_s3_region}"
      etcd-s3-access-key: "${etcd_s3_access_key}"
      etcd-s3-secret-key: "${etcd_s3_secret_key}"
      %{ endif ~}

runcmd:
  - useradd -r -c "etcd user" -s /sbin/nologin -M etcd 2>/dev/null || true
  - sysctl --system
  - systemctl enable --now iscsid
  - mkdir -p /var/log/kube-audit
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
      curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION="${kubernetes_version}" INSTALL_RKE2_TYPE=server sh - && break
      sleep 10
    done
  - systemctl enable --now rke2-server
