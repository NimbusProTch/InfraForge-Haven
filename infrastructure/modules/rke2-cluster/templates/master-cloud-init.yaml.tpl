#cloud-config
# =============================================================================
#  iyziops — first master node (cluster bootstrap)
# =============================================================================
#  Cloud-config format. Drops the RKE2 config body AND every Helm Controller
#  manifest as base64 blobs into write_files. RKE2's in-cluster Helm Controller
#  applies the manifests when rke2-server starts.
#
#  The RKE2 config blob lands at /etc/rancher/rke2/config.yaml.tpl with
#  runtime placeholder __PRIVATE_IP__ still intact. runcmd later seds it
#  into place. The node has no public IPv4 — Haven privatenetworking.
#
#  bootcmd waits for NAT egress (probes TCP 1.1.1.1:443) before apt
#  package install runs, so masters don't race the NAT box boot.
# =============================================================================

# Private-only node bootstrap: Hetzner DHCP on private networks hands
# out a subnet route (10.10.0.0/16 via 10.10.0.1) but no default route
# (since Hetzner's Aug 2025 switch to classless static route / option
# 121) and no DNS. systemd-networkd does not persist a manual `ip route
# add` across its re-renders, so we write a netplan drop-in with the
# default route + Hetzner resolvers, then `netplan apply` to lock it
# in before cloud-init's package_update runs apt. This is the Ubuntu
# equivalent of kube-hetzner's nmcli persistent-route trick.
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
  # ---------- sysctl for RKE2 CIS profile ----------
  - path: /etc/sysctl.d/90-rke2.conf
    permissions: '0644'
    content: |
      vm.panic_on_oom=0
      vm.overcommit_memory=1
      kernel.panic=10
      kernel.panic_on_oops=1

  # ---------- multipath-tools quarantine (Longhorn compatibility) ----------
  # The Hetzner Ubuntu base image ships multipath-tools as an open-iscsi
  # Recommends. Once installed it claims iSCSI block devices into mpath*
  # device-mapper tables, blocking mke2fs on Longhorn volumes with
  # "apparently in use by the system". The pin file below blocks any
  # future apt operation from (re)installing it; the runcmd entry below
  # purges it from the running system.
  - path: /etc/apt/preferences.d/99-no-multipath
    permissions: '0644'
    content: |
      Package: multipath-tools
      Pin: release *
      Pin-Priority: -1

  # /etc/multipath.conf is harmless when multipathd is not installed but
  # provides defense-in-depth: if multipath-tools is ever reinstalled by
  # mistake, this blacklist keeps it from grabbing Longhorn block devices.
  - path: /etc/multipath.conf
    permissions: '0644'
    content: |
      defaults { user_friendly_names yes }
      blacklist {
        devnode "^sd[a-z0-9]+"
        devnode "^dasd[a-z0-9]+"
        devnode "^nvme[0-9]+n[0-9]+"
      }

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
  # Purge multipath-tools BEFORE iscsid starts. Pin file written above
  # blocks future reinstallation. Idempotent / safe if not installed.
  - DEBIAN_FRONTEND=noninteractive apt-get -y purge multipath-tools 2>/dev/null || true
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
    sed "s|__PRIVATE_IP__|$PRIVATE_IP|g" \
      /etc/rancher/rke2/config.yaml.tpl > /etc/rancher/rke2/config.yaml
    chmod 0600 /etc/rancher/rke2/config.yaml
  - |
    set -eu
    for i in 1 2 3 4 5; do
      curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION="${kubernetes_version}" INSTALL_RKE2_TYPE=server sh - && break
      sleep 10
    done
  - systemctl enable --now rke2-server

  # ---------- Pre-install Gateway API CRDs + restart Cilium operator ----------
  # Wait for kubectl + apiserver, fetch the upstream Gateway API
  # experimental-install bundle from kubernetes-sigs (pinned tag), and
  # apply it server-side. The bundle is ~600KB (well over Hetzner's 32KB
  # cloud-init user_data limit) so we fetch at runtime instead of embedding
  # via base64. Then bounce cilium-operator so its one-shot CRD readiness
  # check picks up the new types — without this restart, Gateway resources
  # stay PROGRAMMED=Unknown forever. Idempotent: re-running is a no-op.
  - |
    set -eu
    KUBECTL=/var/lib/rancher/rke2/bin/kubectl
    KUBECONFIG=/etc/rancher/rke2/rke2.yaml
    export KUBECONFIG
    GW_API_VERSION="${gateway_api_version}"
    GW_API_URL="https://github.com/kubernetes-sigs/gateway-api/releases/download/$${GW_API_VERSION}/experimental-install.yaml"
    mkdir -p /var/lib/iyziops
    for i in $(seq 1 60); do
      if [ -x "$KUBECTL" ] && [ -f "$KUBECONFIG" ] && $KUBECTL get nodes >/dev/null 2>&1; then
        break
      fi
      sleep 5
    done
    for i in 1 2 3 4 5; do
      curl -sfL "$GW_API_URL" -o /var/lib/iyziops/gateway-api-crds.yaml && break
      sleep 5
    done
    $KUBECTL apply --server-side --force-conflicts -f /var/lib/iyziops/gateway-api-crds.yaml
    # Wait for cilium-operator to exist before trying to restart it
    for i in $(seq 1 60); do
      if $KUBECTL -n kube-system get deploy cilium-operator >/dev/null 2>&1; then
        $KUBECTL -n kube-system rollout restart deploy/cilium-operator
        break
      fi
      sleep 5
    done
