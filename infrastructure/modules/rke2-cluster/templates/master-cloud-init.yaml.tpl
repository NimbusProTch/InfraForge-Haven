#cloud-config
# =============================================================================
#  iyziops — first master node (cluster bootstrap)
# =============================================================================
#  Cloud-config format. Drops the RKE2 config body AND every Helm Controller
#  manifest as base64 blobs into write_files. RKE2's in-cluster Helm Controller
#  applies the manifests when rke2-server starts.
#
#  The RKE2 config blob lands at /etc/rancher/rke2/config.yaml.tpl with
#  runtime placeholders __PRIVATE_IP__ and __PUBLIC_IP__ still intact. runcmd
#  later seds those into place based on Hetzner metadata.
# =============================================================================

package_update: true
package_upgrade: false
packages:
  - curl
  - jq
  - open-iscsi
  - wireguard-tools

write_files:
  # ---------- sysctl for RKE2 CIS profile ----------
  - path: /etc/sysctl.d/90-rke2.conf
    permissions: '0644'
    content: |
      vm.panic_on_oom=0
      vm.overcommit_memory=1
      kernel.panic=10
      kernel.panic_on_oops=1

  # ---------- kube-apiserver audit policy ----------
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
          resources:
            - group: ""
              resources: ["events", "endpoints", "services", "pods/log", "pods/status"]
            - group: "coordination.k8s.io"
              resources: ["leases"]
        - level: RequestResponse
          resources:
            - group: "rbac.authorization.k8s.io"
              resources: ["clusterroles", "clusterrolebindings", "roles", "rolebindings"]
        - level: Metadata
          resources:
            - group: ""
              resources: ["secrets"]
        - level: RequestResponse
          resources:
            - group: ""
              resources: ["namespaces"]
        - level: Metadata
          resources:
            - group: ""
              resources: ["serviceaccounts/token"]
        - level: Metadata
          resources:
            - group: "argoproj.io"
              resources: ["applications", "applicationsets"]
        - level: Metadata
          verbs: ["create", "update", "patch", "delete"]

  # ---------- RKE2 config template (base64, runtime IPs substituted in runcmd) ----------
  - path: /etc/rancher/rke2/config.yaml.tpl
    permissions: '0600'
    encoding: b64
    content: ${rke2_config_b64}

  # ---------- Helm Controller manifests (base64) — MINIMAL BOOTSTRAP SET ----------
  # Only what the cluster cannot start without (Cilium CNI + Hetzner CCM)
  # plus the ArgoCD bootstrap chain. Longhorn, cert-manager, ClusterIssuers,
  # wildcard cert, and every downstream service live in the GitOps repo as
  # ArgoCD Applications with sync-wave ordering.

  - path: /var/lib/rancher/rke2/server/manifests/rke2-cilium-config.yaml
    permissions: '0600'
    encoding: b64
    content: ${manifest_cilium_config_b64}

  - path: /var/lib/rancher/rke2/server/manifests/hetzner-ccm.yaml
    permissions: '0600'
    encoding: b64
    content: ${manifest_hetzner_ccm_b64}

  - path: /var/lib/rancher/rke2/server/manifests/cert-manager-namespace.yaml
    permissions: '0600'
    encoding: b64
    content: ${manifest_cert_manager_namespace_b64}

  - path: /var/lib/rancher/rke2/server/manifests/longhorn-namespace.yaml
    permissions: '0600'
    encoding: b64
    content: ${manifest_longhorn_namespace_b64}

  - path: /var/lib/rancher/rke2/server/manifests/cloudflare-token-secret.yaml
    permissions: '0600'
    encoding: b64
    content: ${manifest_cloudflare_token_secret_b64}

  - path: /var/lib/rancher/rke2/server/manifests/argocd.yaml
    permissions: '0600'
    encoding: b64
    content: ${manifest_argocd_b64}

  - path: /var/lib/rancher/rke2/server/manifests/argocd-projects.yaml
    permissions: '0600'
    encoding: b64
    content: ${manifest_argocd_projects_b64}

  - path: /var/lib/rancher/rke2/server/manifests/argocd-repo-secret.yaml
    permissions: '0600'
    encoding: b64
    content: ${manifest_argocd_repo_secret_b64}

  - path: /var/lib/rancher/rke2/server/manifests/argocd-root-app.yaml
    permissions: '0600'
    encoding: b64
    content: ${manifest_argocd_root_app_b64}

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
    for i in 1 2 3 4 5; do
      curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION="${kubernetes_version}" INSTALL_RKE2_TYPE=server sh - && break
      sleep 10
    done
  - systemctl enable --now rke2-server
