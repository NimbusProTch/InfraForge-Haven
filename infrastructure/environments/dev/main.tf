# ============================================================
# Haven Platform - Dev Environment (Hetzner Cloud)
# ============================================================
# Vanilla RKE2 cluster (no Rancher dependency):
#   1. Hetzner base infra (network, firewall, LB)
#   2. RKE2 cluster via cloud-init (direct install)
#   3. Kubeconfig retrieval via SSH
#   4. Platform operators via Helm provider
#   5. Platform services (ArgoCD, Keycloak, Harbor, etc.)
# ============================================================

locals {
  node_username = "root"

  # Multi-AZ distribution: even split across zones for etcd quorum safety.
  # With 4 masters (2+2) losing one AZ still leaves 2 nodes = etcd quorum survives.
  # With 3 workers distributed round-robin across zones.
  master_locations = [for i in range(var.master_count) : i % 2 == 0 ? var.location_primary : var.location_secondary]
  worker_locations = [for i in range(var.worker_count) : i % 2 == 0 ? var.location_primary : var.location_secondary]

  # First master gets a static private IP for other nodes to join
  first_master_private_ip = "10.0.1.10"

  # IS5-02: Hostname resolution — sslip.io (dev) or real domain (prod)
  # Toggle: set use_real_domain = true + domain = "yourdomain.com" in terraform.tfvars
  # sslip.io: LB IP encoded in hostname (no DNS record needed, great for dev)
  # real domain: External-DNS + Cloudflare manages DNS automatically (IS5-01)
  lb_dns = module.hetzner_infra.load_balancer_ip
  _sslip_suffix = "${local.lb_dns}.sslip.io"
  _domain_suffix = var.domain

  harbor_host    = var.use_real_domain ? "harbor.${local._domain_suffix}"    : "harbor.${local._sslip_suffix}"
  argocd_host    = var.use_real_domain ? "argocd.${local._domain_suffix}"    : "argocd.${local._sslip_suffix}"
  keycloak_host  = var.use_real_domain ? "keycloak.${local._domain_suffix}"  : "keycloak.${local._sslip_suffix}"
  api_host       = var.use_real_domain ? "api.${local._domain_suffix}"       : "api.${local._sslip_suffix}"
  ui_host        = var.use_real_domain ? "ui.${local._domain_suffix}"        : "ui.${local._sslip_suffix}"
  minio_host     = var.use_real_domain ? "minio.${local._domain_suffix}"     : "minio.${local._sslip_suffix}"
  s3_host        = var.use_real_domain ? "s3.${local._domain_suffix}"        : "s3.${local._sslip_suffix}"
  everest_host   = var.use_real_domain ? "everest.${local._domain_suffix}"   : "everest.${local._sslip_suffix}"
  grafana_host   = var.use_real_domain ? "grafana.${local._domain_suffix}"   : "grafana.${local._sslip_suffix}"
  longhorn_host  = var.use_real_domain ? "longhorn.${local._domain_suffix}"  : "longhorn.${local._sslip_suffix}"
  hubble_host    = var.use_real_domain ? "hubble.${local._domain_suffix}"    : "hubble.${local._sslip_suffix}"
  gitea_host     = var.use_real_domain ? "gitea.${local._domain_suffix}"     : "gitea.${local._sslip_suffix}"
}

# --- 1. SSH Key ---
resource "tls_private_key" "global_key" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "local_sensitive_file" "ssh_private_key_pem" {
  filename        = "${path.module}/id_rsa"
  content         = tls_private_key.global_key.private_key_pem
  file_permission = "0600"
}

# Cluster token for RKE2 node registration
resource "random_password" "cluster_token" {
  length  = 64
  special = false
}

# --- 2. Base Infrastructure (network, firewall, LB — no management node) ---
module "hetzner_infra" {
  source = "../../modules/hetzner-infra"

  environment      = var.environment
  location_primary = var.location_primary
  ssh_public_key   = tls_private_key.global_key.public_key_openssh
  network_cidr     = var.network_cidr
  subnet_cidr      = var.subnet_cidr
  # H1b-1 (P4.1): operator IP allow-list for SSH 22, K8s API 6443, RKE2
  # supervisor 9345. Pre-fix all three were 0.0.0.0/0. Set this in
  # terraform.tfvars (NOT here) to your VPN/office egress CIDRs.
  operator_cidrs         = var.operator_cidrs
  gateway_http_nodeport  = 80
  gateway_https_nodeport = 443
}

# --- 3. RKE2 Cluster Config (cloud-init generation) ---
module "rke2_cluster" {
  source = "../../modules/rke2-cluster"

  cluster_name             = var.cluster_name
  kubernetes_version       = var.kubernetes_version
  cluster_token            = random_password.cluster_token.result
  first_master_private_ip  = local.first_master_private_ip
  lb_ip                    = module.hetzner_infra.load_balancer_ip
  enable_hubble            = true
  cilium_operator_replicas = 1
  disable_kube_proxy       = true
  enable_cis_profile       = true

  # H1b-2 (P4.2): etcd snapshot config. Defaults snapshot daily 02:00 UTC,
  # keep 30 locally. Off-cluster S3 upload (etcd_s3_enabled) is OFF by
  # default — morning operator must set it true and provide R2 / off-host
  # MinIO credentials in tfvars before applying. With it OFF, snapshots
  # exist only on each master's local disk and die with the master.
  etcd_snapshot_schedule  = var.etcd_snapshot_schedule
  etcd_snapshot_retention = var.etcd_snapshot_retention
  etcd_s3_enabled         = var.etcd_s3_enabled
  etcd_s3_endpoint        = var.etcd_s3_endpoint
  etcd_s3_bucket          = var.etcd_s3_bucket
  etcd_s3_folder          = var.etcd_s3_folder
  etcd_s3_region          = var.etcd_s3_region
  etcd_s3_access_key      = var.etcd_s3_access_key
  etcd_s3_secret_key      = var.etcd_s3_secret_key

  # H1a-2: kubectl OIDC integration. Defaults point at the dev cluster
  # Keycloak (haven realm). Operator must ensure haven-kubectl public
  # client exists (see keycloak/haven-realm.json) before tenant admins
  # can `kubectl` against the cluster.
  keycloak_oidc_issuer_url = var.keycloak_oidc_issuer_url
  keycloak_oidc_client_id  = var.keycloak_oidc_client_id
}

# --- 4. Master Nodes ---
resource "hcloud_server" "master" {
  count        = var.master_count
  name         = "haven-master-${var.environment}-${count.index + 1}"
  server_type  = var.master_server_type
  image        = var.os_image
  location     = local.master_locations[count.index]
  ssh_keys     = [module.hetzner_infra.ssh_key_id]
  firewall_ids = [module.hetzner_infra.firewall_id]

  # Cloud-init: minimal setup (RKE2 installed via SSH post-provisioning)
  user_data = <<-EOT
    #!/bin/bash
    apt-get update -qq && apt-get install -y -qq curl jq open-iscsi
    useradd -r -c "etcd user" -s /sbin/nologin -M etcd 2>/dev/null || true
    systemctl enable --now iscsid
    cat > /etc/sysctl.d/90-rke2.conf << 'EOF'
    vm.panic_on_oom=0
    vm.overcommit_memory=1
    kernel.panic=10
    kernel.panic_on_oops=1
    EOF
    sysctl --system
  EOT

  labels = {
    role        = "master"
    environment = var.environment
    project     = "haven"
    node_index  = tostring(count.index + 1)
  }
}

# Attach masters to private network
resource "hcloud_server_network" "master" {
  count     = var.master_count
  server_id = hcloud_server.master[count.index].id
  subnet_id = module.hetzner_infra.subnet_id
  # First master gets static IP for cluster join
  ip = count.index == 0 ? local.first_master_private_ip : null
}

# --- 5. Worker Nodes ---
resource "hcloud_server" "worker" {
  count        = var.worker_count
  name         = "haven-worker-${var.environment}-${count.index + 1}"
  server_type  = var.worker_server_type
  image        = var.os_image
  location     = local.worker_locations[count.index]
  ssh_keys     = [module.hetzner_infra.ssh_key_id]
  firewall_ids = [module.hetzner_infra.firewall_id]

  # Cloud-init: minimal setup (RKE2 installed via SSH post-provisioning)
  user_data = <<-EOT
    #!/bin/bash
    apt-get update -qq && apt-get install -y -qq curl jq open-iscsi
    systemctl enable --now iscsid
    cat > /etc/sysctl.d/90-rke2.conf << 'EOF'
    vm.panic_on_oom=0
    vm.overcommit_memory=1
    kernel.panic=10
    kernel.panic_on_oops=1
    EOF
    sysctl --system
  EOT

  labels = {
    role        = "worker"
    environment = var.environment
    project     = "haven"
    node_index  = tostring(count.index + 1)
  }

  depends_on = [hcloud_server.master, hcloud_server_network.master]
}

resource "hcloud_server_network" "worker" {
  count     = var.worker_count
  server_id = hcloud_server.worker[count.index].id
  subnet_id = module.hetzner_infra.subnet_id
}

# --- 6. Load Balancer Targets ---
resource "hcloud_load_balancer_target" "master" {
  count            = var.master_count
  type             = "server"
  load_balancer_id = module.hetzner_infra.load_balancer_id
  server_id        = hcloud_server.master[count.index].id
  use_private_ip   = true
  depends_on       = [hcloud_server_network.master]
}

resource "hcloud_load_balancer_target" "worker" {
  count            = var.worker_count
  type             = "server"
  load_balancer_id = module.hetzner_infra.load_balancer_id
  server_id        = hcloud_server.worker[count.index].id
  use_private_ip   = true
  depends_on       = [hcloud_server_network.worker]
}

# --- 7a. Install RKE2 on First Master (via SSH) ---
resource "ssh_resource" "install_rke2_first_master" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "20m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      # Wait for cloud-init to finish
      cloud-init status --wait 2>/dev/null || sleep 30

      PRIVATE_IP=$(ip -4 addr show | grep -oP "(?<=inet\\s)10\\.\\d+\\.\\d+\\.\\d+" | head -1)
      PUBLIC_IP=$(curl -sf http://169.254.169.254/hetzner/v1/metadata/public-ipv4)
      echo "IPs: private=$PRIVATE_IP public=$PUBLIC_IP"

      mkdir -p /etc/rancher/rke2
      cat > /etc/rancher/rke2/config.yaml << RKEEOF
token: ${random_password.cluster_token.result}
cluster-init: true
node-ip: $PRIVATE_IP
node-external-ip: $PUBLIC_IP
tls-san:
  - ${module.hetzner_infra.load_balancer_ip}
  - $PRIVATE_IP
  - $PUBLIC_IP
cni: cilium
disable:
  - rke2-ingress-nginx
disable-kube-proxy: true
profile: cis
protect-kernel-defaults: true
write-kubeconfig-mode: "0644"
secrets-encryption: true
${var.enable_oidc ? <<-OIDCEOF
kube-apiserver-arg:
  - "oidc-issuer-url=https://${local.keycloak_host}/realms/haven"
  - "oidc-client-id=${var.keycloak_oidc_client_id}"
  - "oidc-username-claim=preferred_username"
  - "oidc-groups-claim=groups"
  - "oidc-username-prefix=oidc:"
  - "oidc-groups-prefix=oidc:"
OIDCEOF
: ""}
RKEEOF

      mkdir -p /var/lib/rancher/rke2/server/manifests
      cat > /var/lib/rancher/rke2/server/manifests/rke2-cilium-config.yaml << CILEOF
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: rke2-cilium
  namespace: kube-system
spec:
  valuesContent: |-
    kubeProxyReplacement: true
    k8sServiceHost: "$PRIVATE_IP"
    k8sServicePort: "6443"
    operator:
      replicas: 1
    gatewayAPI:
      enabled: true
    hubble:
      enabled: true
      relay:
        enabled: true
      ui:
        enabled: true
    ipam:
      mode: kubernetes
    encryption:
      enabled: ${var.enable_wireguard_encryption ? "true" : "false"}
      type: wireguard
      wireguard:
        userspaceFallback: true
    tolerations:
      - operator: Exists
CILEOF

      # Insecure registry config for Harbor (HTTP-only dev)
      cat > /etc/rancher/rke2/registries.yaml << REGEOF
mirrors:
  ${local.harbor_host}:
    endpoint:
      - "https://${local.harbor_host}"
REGEOF

      curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION=${var.kubernetes_version} sh -
      systemctl enable rke2-server.service
      systemctl start rke2-server.service

      # Wait for API
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      export PATH=$PATH:/var/lib/rancher/rke2/bin
      for i in $(seq 1 120); do
        if kubectl get nodes >/dev/null 2>&1; then
          echo "RKE2_FIRST_MASTER_READY"
          break
        fi
        sleep 5
      done
    '
  EOT
  )]

  depends_on = [
    hcloud_server.master,
    hcloud_server_network.master,
  ]
}

# --- 7b. Install RKE2 on Other Masters ---
resource "ssh_resource" "install_rke2_other_masters" {
  count       = var.master_count - 1
  host        = hcloud_server.master[count.index + 1].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "20m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      cloud-init status --wait 2>/dev/null || sleep 30
      PRIVATE_IP=$(ip -4 addr show | grep -oP "(?<=inet\\s)10\\.\\d+\\.\\d+\\.\\d+" | head -1)
      PUBLIC_IP=$(curl -sf http://169.254.169.254/hetzner/v1/metadata/public-ipv4)

      useradd -r -c "etcd user" -s /sbin/nologin -M etcd 2>/dev/null || true
      mkdir -p /etc/rancher/rke2
      cat > /etc/rancher/rke2/config.yaml << RKEEOF
token: ${random_password.cluster_token.result}
server: https://${local.first_master_private_ip}:9345
node-ip: $PRIVATE_IP
node-external-ip: $PUBLIC_IP
tls-san:
  - ${module.hetzner_infra.load_balancer_ip}
  - $PRIVATE_IP
  - $PUBLIC_IP
cni: cilium
disable:
  - rke2-ingress-nginx
disable-kube-proxy: true
profile: cis
protect-kernel-defaults: true
write-kubeconfig-mode: "0644"
secrets-encryption: true
${var.enable_oidc ? <<-OIDCEOF
kube-apiserver-arg:
  - "oidc-issuer-url=https://${local.keycloak_host}/realms/haven"
  - "oidc-client-id=${var.keycloak_oidc_client_id}"
  - "oidc-username-claim=preferred_username"
  - "oidc-groups-claim=groups"
  - "oidc-username-prefix=oidc:"
  - "oidc-groups-prefix=oidc:"
OIDCEOF
: ""}
RKEEOF

      # Insecure registry config for Harbor (HTTP-only dev)
      cat > /etc/rancher/rke2/registries.yaml << REGEOF
mirrors:
  ${local.harbor_host}:
    endpoint:
      - "https://${local.harbor_host}"
REGEOF

      curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION=${var.kubernetes_version} sh -
      systemctl enable rke2-server.service
      systemctl start rke2-server.service
      echo "MASTER_${count.index + 2}_STARTED"
    '
  EOT
  )]

  depends_on = [ssh_resource.install_rke2_first_master]
}

# --- 7c. Install RKE2 Agent on Workers ---
resource "ssh_resource" "install_rke2_workers" {
  count       = var.worker_count
  host        = hcloud_server.worker[count.index].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "20m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      cloud-init status --wait 2>/dev/null || sleep 30
      PRIVATE_IP=$(ip -4 addr show | grep -oP "(?<=inet\\s)10\\.\\d+\\.\\d+\\.\\d+" | head -1)
      PUBLIC_IP=$(curl -sf http://169.254.169.254/hetzner/v1/metadata/public-ipv4)

      mkdir -p /etc/rancher/rke2
      cat > /etc/rancher/rke2/config.yaml << RKEEOF
token: ${random_password.cluster_token.result}
server: https://${local.first_master_private_ip}:9345
node-ip: $PRIVATE_IP
node-external-ip: $PUBLIC_IP
profile: cis
protect-kernel-defaults: true
RKEEOF

      # Insecure registry config for Harbor (HTTP-only dev)
      cat > /etc/rancher/rke2/registries.yaml << REGEOF
mirrors:
  ${local.harbor_host}:
    endpoint:
      - "https://${local.harbor_host}"
REGEOF

      curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=agent INSTALL_RKE2_VERSION=${var.kubernetes_version} sh -
      systemctl enable rke2-agent.service
      systemctl start rke2-agent.service
      echo "WORKER_${count.index + 1}_STARTED"
    '
  EOT
  )]

  depends_on = [ssh_resource.install_rke2_first_master]
}

# --- 7d. Retrieve Kubeconfig from First Master ---
resource "ssh_resource" "kubeconfig" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "20m"

  commands = [
    # Wait for RKE2 API to be ready (cloud-init can take 5-10 min)
    <<-EOT
      for i in $(seq 1 120); do
        if [ -f /etc/rancher/rke2/rke2.yaml ]; then
          if /var/lib/rancher/rke2/bin/kubectl --kubeconfig=/etc/rancher/rke2/rke2.yaml get nodes >/dev/null 2>&1; then
            echo "RKE2_READY"
            break
          fi
        fi
        sleep 10
      done
    EOT
    ,
    "cat /etc/rancher/rke2/rke2.yaml",
  ]

  depends_on = [ssh_resource.install_rke2_first_master]
}

# Process kubeconfig: replace 127.0.0.1 with LB IP for external access
locals {
  raw_kubeconfig = ssh_resource.kubeconfig.result
  kubeconfig = replace(
    local.raw_kubeconfig,
    "https://127.0.0.1:6443",
    "https://${module.hetzner_infra.load_balancer_ip}:6443"
  )
}

resource "local_sensitive_file" "kubeconfig" {
  filename        = "${path.module}/kubeconfig"
  content         = local.kubeconfig
  file_permission = "0600"
}

# --- 8. Wait for All Nodes Ready ---
resource "ssh_resource" "wait_cluster_ready" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "30m"

  commands = [
    <<-EOT
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      export PATH=$PATH:/var/lib/rancher/rke2/bin
      EXPECTED_NODES=${var.master_count + var.worker_count}
      echo "Waiting for $EXPECTED_NODES nodes to be Ready..."
      for i in $(seq 1 180); do
        READY=$(kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready" || echo "0")
        echo "Ready nodes: $READY / $EXPECTED_NODES (attempt $i)"
        if [ "$READY" -ge "$EXPECTED_NODES" ]; then
          echo "ALL_NODES_READY"
          kubectl get nodes -o wide
          break
        fi
        sleep 10
      done
    EOT
  ]

  depends_on = [
    ssh_resource.kubeconfig,
    ssh_resource.install_rke2_other_masters,
    ssh_resource.install_rke2_workers,
  ]
}

# --- 9. Node Topology Labels (Haven Check #1: Multi-AZ) ---
resource "ssh_resource" "node_topology_labels" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = concat(
    [for i in range(var.master_count) :
      "export KUBECONFIG=/etc/rancher/rke2/rke2.yaml && /var/lib/rancher/rke2/bin/kubectl label node haven-master-${var.environment}-${i + 1} topology.kubernetes.io/zone=${local.master_locations[i]} topology.kubernetes.io/region=eu --overwrite"
    ],
    [for i in range(var.worker_count) :
      "export KUBECONFIG=/etc/rancher/rke2/rke2.yaml && /var/lib/rancher/rke2/bin/kubectl label node haven-worker-${var.environment}-${i + 1} topology.kubernetes.io/zone=${local.worker_locations[i]} topology.kubernetes.io/region=eu --overwrite"
    ]
  )

  depends_on = [ssh_resource.wait_cluster_ready]
}

# ============================================================
# Platform Operators (via Helm provider)
# ============================================================

# --- 9b. CIS PodSecurity: label system namespaces as privileged ---
# RKE2 CIS profile enforces "restricted" PodSecurity by default.
# Storage/operator namespaces need "privileged" to run DaemonSets with hostPath.
resource "ssh_resource" "namespace_security_labels" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = [
    <<-EOT
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      # Create namespaces and label as privileged (CIS override for system components)
      # everest/everest-monitoring/everest-olm: Percona Everest OLM + operators need privileged
      for NS in longhorn-system cert-manager monitoring logging harbor-system minio-system \
                argocd everest-system everest everest-monitoring everest-olm \
                cnpg-system redis-system rabbitmq-system keycloak \
                haven-system haven-builds haven-gateway gitea-system; do
        $K create namespace $NS --dry-run=client -o yaml | $K apply -f -
        $K label namespace $NS \
          pod-security.kubernetes.io/enforce=privileged \
          pod-security.kubernetes.io/audit=privileged \
          pod-security.kubernetes.io/warn=privileged \
          --overwrite
      done

      # Everest Helm chart expects to own these namespaces — add Helm labels
      for NS in everest everest-monitoring everest-olm; do
        $K label namespace $NS app.kubernetes.io/managed-by=Helm --overwrite
        $K annotate namespace $NS \
          meta.helm.sh/release-name=everest \
          meta.helm.sh/release-namespace=everest-system \
          --overwrite
      done
      echo "All system namespaces labeled privileged + Everest Helm labels"
    EOT
  ]

  depends_on = [ssh_resource.wait_cluster_ready]
}

# --- 10. Longhorn Storage (Haven Check #10: RWX) ---
resource "helm_release" "longhorn" {
  count            = var.enable_longhorn ? 1 : 0
  name             = "longhorn"
  namespace        = "longhorn-system"
  create_namespace = false  # Created by namespace_security_labels with privileged PSA
  repository       = "https://charts.longhorn.io"
  chart            = "longhorn"
  version          = var.longhorn_version
  timeout          = 900
  wait             = true

  values = [templatefile("${path.module}/helm-values/longhorn.yaml", {
    replica_count = var.worker_count >= 3 ? 3 : var.worker_count
  })]

  depends_on = [ssh_resource.namespace_security_labels]
}

# --- 10b. Wait for Longhorn CSI Plugin to be Ready on ALL nodes ---
# Critical: Harbor, MinIO, Monitoring require PVCs. If Longhorn CSI plugin
# DaemonSet is not fully Running when PVCs are created, volumes fail to attach.
# This gate ensures all nodes have the CSI driver registered before proceeding.
resource "ssh_resource" "wait_longhorn_ready" {
  count       = var.enable_longhorn ? 1 : 0
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "15m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl
      EXPECTED=${var.master_count + var.worker_count}
      echo "Waiting for Longhorn CSI plugin on all $EXPECTED nodes..."
      for i in $(seq 1 90); do
        READY=$($K get pods -n longhorn-system -l app=longhorn-csi-plugin \
          --no-headers 2>/dev/null | grep -c "3/3" || echo 0)
        echo "  CSI plugin ready: $READY/$EXPECTED nodes (attempt $i)"
        if [ "$READY" -ge "$EXPECTED" ]; then
          echo "LONGHORN_CSI_READY"
          break
        fi
        sleep 10
      done
    '
  EOT
  )]

  depends_on = [helm_release.longhorn]
}

# --- 11. Cert-Manager (Haven Check #12: Auto HTTPS) ---
resource "helm_release" "cert_manager" {
  count            = var.enable_cert_manager ? 1 : 0
  name             = "cert-manager"
  namespace        = "cert-manager"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://charts.jetstack.io"
  chart            = "cert-manager"
  version          = var.cert_manager_version
  timeout          = 600
  wait             = true

  set {
    name  = "installCRDs"
    value = "true"
  }

  # Gateway API support: cert-manager v1.20+ needs config.enableGatewayAPI
  # (the old featureGates flag was removed). Without this, ACME HTTP-01
  # challenges stay "pending" with "gateway api is not enabled" and
  # "skipping disabled controller: gateway-shim" in logs.
  set {
    name  = "config.enableGatewayAPI"
    value = "true"
  }

  depends_on = [helm_release.longhorn]
}

# --- 12. Kube-Prometheus-Stack (Haven Check #14: Monitoring) ---
# Prometheus, Grafana, and AlertManager each create PVCs via Longhorn.
resource "helm_release" "monitoring" {
  count            = var.enable_monitoring ? 1 : 0
  name             = "kube-prometheus-stack"
  namespace        = "monitoring"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  version          = var.monitoring_version
  timeout          = 900
  wait             = true

  values = [templatefile("${path.module}/helm-values/monitoring.yaml", {
    storage_class          = "longhorn"
    grafana_admin_password = var.grafana_admin_password
  })]

  depends_on = [ssh_resource.wait_longhorn_ready]
}

# --- 13. Logging (Haven Check #13: Log Aggregation) ---
# Loki uses a PVC for log persistence — must wait for Longhorn CSI to be ready.
resource "helm_release" "loki_stack" {
  count            = var.enable_logging ? 1 : 0
  name             = "loki-stack"
  namespace        = "logging"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://grafana.github.io/helm-charts"
  chart            = "loki-stack"
  version          = var.logging_version
  timeout          = 600
  wait             = true

  values = [templatefile("${path.module}/helm-values/logging.yaml", {})]

  # wait_longhorn_ready ensures CSI plugin is running on all nodes before
  # any PVC is created, preventing volume attachment failures.
  depends_on = [ssh_resource.wait_longhorn_ready]
}

# --- 14. Harbor Image Registry ---
# Harbor creates multiple PVCs (registry, database, redis, jobservice).
# All must be schedulable — requires Longhorn CSI to be fully registered.
resource "helm_release" "harbor" {
  count            = var.enable_harbor ? 1 : 0
  name             = "harbor"
  namespace        = "harbor-system"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://helm.goharbor.io"
  chart            = "harbor"
  version          = var.harbor_version
  timeout          = 1500
  wait             = true

  values = [templatefile("${path.module}/helm-values/harbor.yaml", {
    harbor_host            = local.harbor_host
    admin_password         = var.harbor_admin_password
    registry_storage_size  = var.harbor_registry_storage_size
  })]

  depends_on = [ssh_resource.wait_longhorn_ready, helm_release.cert_manager]
}

# --- 15. MinIO Object Storage ---
# MinIO creates a PVC for object storage — requires Longhorn CSI.
resource "helm_release" "minio" {
  count            = var.enable_minio ? 1 : 0
  name             = "minio"
  namespace        = "minio-system"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://charts.min.io"
  chart            = "minio"
  version          = var.minio_version
  timeout          = 900
  wait             = true

  values = [templatefile("${path.module}/helm-values/minio.yaml", {
    root_user           = var.minio_root_user
    root_password       = var.minio_root_password
    storage_size        = var.minio_storage_size
    kms_secret_key      = var.minio_kms_secret_key
    kms_auto_encryption = var.minio_kms_auto_encryption
  })]

  depends_on = [ssh_resource.wait_longhorn_ready]
}

# --- 16. ArgoCD ---
resource "helm_release" "argocd" {
  count            = var.enable_argocd ? 1 : 0
  name             = "argocd"
  namespace        = "argocd"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = var.argocd_version
  timeout          = 900
  wait             = true

  values = [templatefile("${path.module}/helm-values/argocd.yaml", {
    argocd_host = local.argocd_host
  })]

  depends_on = [helm_release.cert_manager]
}

# --- 17. Percona Everest (Database Platform: PostgreSQL, MySQL, MongoDB) ---
# Everest installs via OLM (Operator Lifecycle Manager), which provisions
# operators asynchronously — Helm returns before operators are Running.
# wait=false: OLM installs operators async; readiness gate is in wait_everest_ready below.
# disable_webhooks=true: Everest post-install hooks create PodSchedulingPolicy CRs that
# go through the Everest operator's admission webhook. At hook time the operator is still
# starting, so the webhook is not ready → hook fails with "context deadline exceeded".
# The PSP CRs are instead created in wait_everest_ready after the operator is confirmed Ready.
resource "helm_release" "everest" {
  count             = var.enable_everest ? 1 : 0
  name              = "everest"
  namespace         = "everest-system"
  create_namespace  = false  # Created by namespace_security_labels
  repository        = "https://percona.github.io/percona-helm-charts"
  chart             = "everest"
  version           = var.everest_version
  timeout           = 600   # 10 min — hooks disabled, just chart apply
  wait              = false
  disable_webhooks  = true  # Skip pre/post hooks; PSPs applied in wait_everest_ready

  depends_on = [ssh_resource.namespace_security_labels, ssh_resource.wait_longhorn_ready]
}

# --- 17b. Wait for Everest Operator pods to be Ready ---
# Everest uses OLM for operator lifecycle management. We just need the core
# everest-operator and everest-server pods to be Running.
# CNPG is installed separately via helm_release.cnpg (not via Everest/OLM).
resource "ssh_resource" "wait_everest_ready" {
  count       = var.enable_everest ? 1 : 0
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "10m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      echo "Waiting for Everest operator + server pods..."
      for i in $(seq 1 60); do
        READY=$($K get pods -n everest-system --no-headers 2>/dev/null | grep -c "1/1" || echo 0)
        if [ "$READY" -ge "2" ]; then
          echo "EVEREST_READY: $READY pods running"
          break
        fi
        echo "  Everest pods not ready yet (attempt $i, found $READY/2)"
        sleep 10
      done

      # Create default PodSchedulingPolicy CRs (skipped during helm install via disable_webhooks).
      # Applied here after the operator is confirmed Running — its admission webhook is now ready.
      echo "Applying default PodSchedulingPolicy resources..."
      for PSP in everest-default-mysql everest-default-postgresql everest-default-mongodb; do
        if ! $K get podschedulingpolicy "$PSP" >/dev/null 2>&1; then
          echo "  Creating $PSP"
        else
          echo "  $PSP already exists, skipping"
        fi
      done
      cat <<YAML | $K apply --server-side --force-conflicts -f - 2>&1 || true
apiVersion: everest.percona.com/v1alpha1
kind: PodSchedulingPolicy
metadata:
  name: everest-default-mysql
  finalizers: [everest.percona.com/readonly-protection]
spec:
  engineType: pxc
  affinityConfig:
    pxc:
      engine:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - podAffinityTerm: {topologyKey: kubernetes.io/hostname}
              weight: 1
      proxy:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - podAffinityTerm: {topologyKey: kubernetes.io/hostname}
              weight: 1
---
apiVersion: everest.percona.com/v1alpha1
kind: PodSchedulingPolicy
metadata:
  name: everest-default-postgresql
  finalizers: [everest.percona.com/readonly-protection]
spec:
  engineType: postgresql
  affinityConfig:
    postgresql:
      engine:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - podAffinityTerm: {topologyKey: kubernetes.io/hostname}
              weight: 1
      proxy:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - podAffinityTerm: {topologyKey: kubernetes.io/hostname}
              weight: 1
---
apiVersion: everest.percona.com/v1alpha1
kind: PodSchedulingPolicy
metadata:
  name: everest-default-mongodb
  finalizers: [everest.percona.com/readonly-protection]
spec:
  engineType: psmdb
  affinityConfig:
    psmdb:
      engine:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - podAffinityTerm: {topologyKey: kubernetes.io/hostname}
              weight: 1
      proxy:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - podAffinityTerm: {topologyKey: kubernetes.io/hostname}
              weight: 1
      configServer:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - podAffinityTerm: {topologyKey: kubernetes.io/hostname}
              weight: 1
YAML

      # Approve all Manual-mode OLM InstallPlans in the everest namespace.
      # Everest 1.13 ships Percona operator subscriptions with Manual approval;
      # without this step the Percona PG/MongoDB/XtraDB operators never get
      # installed and DatabaseEngine CRs stay in "not installed" state forever,
      # blocking all tenant DB provisioning. Idempotent: skips already-approved.
      # Hard-fails if 3 Percona pods are not Running within 5 min so CI catches
      # regressions early (instead of silently leaving the cluster broken).
      echo "Approving Everest OLM InstallPlans..."
      PERCONA_READY=0
      for i in $(seq 1 30); do
        IPS=$($K get installplans -n everest -o jsonpath="{.items[*].metadata.name}" 2>/dev/null || echo "")
        if [ -n "$IPS" ]; then
          for IP in $IPS; do
            APPROVED=$($K get installplan $IP -n everest -o jsonpath="{.spec.approved}" 2>/dev/null || echo "false")
            if [ "$APPROVED" != "true" ]; then
              $K patch installplan $IP -n everest --type=merge -p "{\"spec\":{\"approved\":true}}" >/dev/null 2>&1 || true
              echo "  approved $IP"
            fi
          done
        fi
        READY=$($K get pods -n everest --no-headers 2>/dev/null | grep -c "1/1" 2>/dev/null || echo 0)
        if [ -z "$READY" ]; then READY=0; fi
        if [ "$READY" -ge "3" ]; then
          echo "PERCONA_OPERATORS_READY: $READY/3 pods running"
          PERCONA_READY=1
          break
        fi
        echo "  waiting for Percona operators ($READY/3 ready, attempt $i)"
        sleep 10
      done
      if [ "$PERCONA_READY" != "1" ]; then
        echo "ERROR: Percona operators did not become Running within 5 minutes."
        echo "Check: kubectl get pods -n everest; kubectl get installplans -n everest"
        exit 1
      fi

      echo "Everest setup complete."
    '
  EOT
  )]

  depends_on = [helm_release.everest]
}

# --- 18. Redis Operator (OpsTree) ---
resource "helm_release" "redis_operator" {
  count            = var.enable_redis_operator ? 1 : 0
  name             = "redis-operator"
  namespace        = "redis-system"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://ot-container-kit.github.io/helm-charts"
  chart            = "redis-operator"
  version          = var.redis_operator_version
  timeout          = 600
  wait             = true

  depends_on = [ssh_resource.namespace_security_labels]
}

# --- 18b. Platform Redis (haven-redis) ---
# Shared Redis instance used by haven-api for: slowapi rate limiting storage,
# git-worker FIFO queue, and other platform-level caches. Passwordless by
# design — tenant isolation is via CNP, and the Redis port is not exposed
# outside the cluster. For prod: switch to password auth + ACLs.
resource "ssh_resource" "platform_redis" {
  count       = var.enable_redis_operator ? 1 : 0
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "3m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      echo "Waiting for Redis operator CRD to be established..."
      for i in $(seq 1 30); do
        if $K get crd redis.redis.redis.opstreelabs.in >/dev/null 2>&1; then
          break
        fi
        sleep 2
      done

      echo "Applying platform haven-redis CR..."
      cat <<REDIS | $K apply --server-side --force-conflicts -f -
apiVersion: redis.redis.opstreelabs.in/v1beta2
kind: Redis
metadata:
  name: haven-redis
  namespace: redis-system
spec:
  kubernetesConfig:
    image: quay.io/opstree/redis:v7.0.15
    imagePullPolicy: IfNotPresent
    resources:
      requests:
        cpu: 50m
        memory: 64Mi
      limits:
        cpu: 200m
        memory: 256Mi
  redisExporter:
    enabled: false
    image: quay.io/opstree/redis-exporter:v1.44.0
REDIS

      echo "Waiting for haven-redis-0 pod Running..."
      REDIS_READY=0
      for i in $(seq 1 30); do
        STATUS=$($K get pod haven-redis-0 -n redis-system -o jsonpath="{.status.phase}" 2>/dev/null || echo "")
        if [ "$STATUS" = "Running" ]; then
          echo "PLATFORM_REDIS_READY"
          REDIS_READY=1
          break
        fi
        sleep 5
      done
      if [ "$REDIS_READY" != "1" ]; then
        echo "ERROR: haven-redis-0 did not become Running within 150s."
        exit 1
      fi
    '
  EOT
  )]

  depends_on = [helm_release.redis_operator]
}

# --- 19. RabbitMQ Cluster Operator (official, NOT Bitnami) ---
resource "ssh_resource" "rabbitmq_operator" {
  count       = var.enable_rabbitmq_operator ? 1 : 0
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = [
    <<-EOT
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      /var/lib/rancher/rke2/bin/kubectl apply -f "https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml"
      echo "RabbitMQ Cluster Operator installed"
    EOT
  ]

  depends_on = [ssh_resource.namespace_security_labels]
}

# --- 19b. CloudNativePG Operator (for Keycloak PostgreSQL) ---
# Installed directly via Helm chart, independent of Percona Everest/OLM.
# Everest 1.13.0 does NOT auto-install CNPG — it requires explicit DB engine provisioning.
resource "helm_release" "cnpg" {
  count            = var.enable_keycloak ? 1 : 0
  name             = "cloudnative-pg"
  namespace        = "cnpg-system"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://cloudnative-pg.github.io/charts"
  chart            = "cloudnative-pg"
  version          = var.cnpg_version
  timeout          = 600
  wait             = true

  depends_on = [ssh_resource.namespace_security_labels]
}

# Wait for CNPG CRD + operator pod to be ready before creating CNPG Cluster
resource "ssh_resource" "wait_cnpg_ready" {
  count       = var.enable_keycloak ? 1 : 0
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "10m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      echo "Waiting for CNPG CRD..."
      for i in $(seq 1 60); do
        if $K get crd clusters.postgresql.cnpg.io >/dev/null 2>&1; then
          echo "CNPG_CRD_READY"; break
        fi
        sleep 5
      done

      echo "Waiting for CNPG operator pod..."
      for i in $(seq 1 60); do
        READY=$($K get pods -n cnpg-system -l app.kubernetes.io/name=cloudnative-pg \
          --no-headers 2>/dev/null | grep -c "1/1" || echo 0)
        if [ "$READY" -ge "1" ]; then
          echo "CNPG_OPERATOR_READY"; break
        fi
        sleep 5
      done
    '
  EOT
  )]

  depends_on = [helm_release.cnpg]
}

# --- 20. Keycloak (Production mode + CNPG PostgreSQL) ---
# Deploy chain:
#   cnpg → wait_cnpg_ready → keycloak_db (CNPG Cluster) → wait_keycloak_db_ready → keycloak

# Step 1: Create the Keycloak PostgreSQL database via CNPG Cluster CRD.
# Requires CNPG operator to be running (gated by wait_everest_ready).
resource "helm_release" "keycloak_db" {
  count            = var.enable_keycloak ? 1 : 0
  name             = "keycloak-db"
  namespace        = "keycloak"
  create_namespace = false  # Created by namespace_security_labels
  chart            = "${path.module}/../../charts/cnpg-cluster"
  timeout          = 600
  wait             = true

  set {
    name  = "name"
    value = "keycloak-db"
  }
  set {
    name  = "instances"
    value = "1"
  }
  set {
    name  = "database"
    value = "keycloak"
  }
  set {
    name  = "owner"
    value = "keycloak"
  }
  set {
    name  = "storage.size"
    value = "10Gi"
  }

  # wait_cnpg_ready ensures CNPG CRD + operator pod are running.
  # wait_longhorn_ready ensures Longhorn CSI can provision the 10Gi PVC.
  depends_on = [ssh_resource.wait_cnpg_ready, ssh_resource.wait_longhorn_ready]
}

# Step 2: Wait for the CNPG primary pod to be Running before deploying Keycloak.
# Keycloak needs the DB to accept connections on startup — if the primary is not
# Ready, Keycloak will fail to connect and enter CrashLoopBackOff.
resource "ssh_resource" "wait_keycloak_db_ready" {
  count       = var.enable_keycloak ? 1 : 0
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "10m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl
      echo "Waiting for keycloak-db CNPG primary pod..."
      for i in $(seq 1 60); do
        READY=$($K get pods -n keycloak -l cnpg.io/cluster=keycloak-db,role=primary \
          --no-headers 2>/dev/null | grep -c "1/1" || echo 0)
        if [ "$READY" -ge "1" ]; then
          echo "KEYCLOAK_DB_PRIMARY_READY"
          break
        fi
        echo "  DB primary not ready yet (attempt $i)"
        sleep 10
      done
    '
  EOT
  )]

  depends_on = [helm_release.keycloak_db]
}

# Step 3: Deploy Keycloak only after the CNPG primary is Ready.
resource "helm_release" "keycloak" {
  count            = var.enable_keycloak ? 1 : 0
  name             = "keycloak"
  namespace        = "keycloak"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://codecentric.github.io/helm-charts"
  chart            = "keycloakx"
  version          = var.keycloak_chart_version
  timeout          = 600
  wait             = true

  values = [templatefile("${path.module}/helm-values/keycloak.yaml", {
    keycloak_host  = local.keycloak_host
    admin_password = var.keycloak_admin_password
    db_secret_name = "keycloak-db-app"  # CNPG auto-creates this Secret
  })]

  depends_on = [ssh_resource.wait_keycloak_db_ready]
}

# --- 20b. Haven Platform Database (CNPG) ---
# The haven-api application database. Same pattern as keycloak_db above.
resource "helm_release" "haven_platform_db" {
  count            = 1
  name             = "haven-platform-db"
  namespace        = "cnpg-system"
  create_namespace = false
  chart            = "${path.module}/../../charts/cnpg-cluster"
  timeout          = 600
  wait             = true

  set {
    name  = "name"
    value = "haven-platform"
  }
  set {
    name  = "instances"
    value = "1"
  }
  set {
    name  = "database"
    value = "haven_platform"
  }
  set {
    name  = "owner"
    value = "haven"
  }
  set {
    name  = "storage.size"
    value = "20Gi"
  }

  depends_on = [ssh_resource.wait_cnpg_ready, ssh_resource.wait_longhorn_ready]
}

resource "ssh_resource" "wait_haven_platform_db_ready" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "10m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl
      echo "Waiting for haven-platform CNPG primary pod..."
      for i in $(seq 1 60); do
        READY=$($K get pods -n cnpg-system -l cnpg.io/cluster=haven-platform,role=primary \
          --no-headers 2>/dev/null | grep -c "1/1" || echo 0)
        if [ "$$READY" -ge "1" ]; then
          echo "HAVEN_PLATFORM_DB_READY"
          break
        fi
        echo "  DB primary not ready yet (attempt $$i)"
        sleep 10
      done
    '
  EOT
  )]

  depends_on = [helm_release.haven_platform_db]
}

# --- 20c. Keycloak Realm Bootstrap ---
# Creates haven realm, haven-ui client, platform-admin role, admin user.
# Runs AFTER Keycloak pod is ready. Idempotent (safe to re-run).
resource "ssh_resource" "keycloak_realm_bootstrap" {
  count       = var.enable_keycloak ? 1 : 0
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "10m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      echo "Waiting for Keycloak pod to be ready..."
      for i in $(seq 1 60); do
        READY=$($K get pods -n keycloak -l app.kubernetes.io/name=keycloakx \
          --no-headers 2>/dev/null | grep -c "1/1" || echo 0)
        if [ "$$READY" -ge "1" ]; then
          echo "KEYCLOAK_POD_READY"
          break
        fi
        echo "  Keycloak not ready yet (attempt $$i)"
        sleep 10
      done

      KC_IP=$($K get svc keycloak-keycloakx-http -n keycloak -o jsonpath="{.spec.clusterIP}" 2>/dev/null || echo "")
      if [ -z "$$KC_IP" ]; then
        echo "ERROR: Could not get Keycloak ClusterIP"
        exit 1
      fi
      KC_URL="http://$$KC_IP:80"
      ADMIN_PASS="${var.keycloak_admin_password}"

      echo "Getting admin token..."
      for i in $(seq 1 10); do
        TOKEN=$(curl -sf -X POST "$$KC_URL/realms/master/protocol/openid-connect/token" \
          -d "grant_type=password&client_id=admin-cli&username=admin&password=$$ADMIN_PASS" \
          2>/dev/null | jq -r ".access_token" 2>/dev/null || echo "")
        if [ -n "$$TOKEN" ] && [ "$$TOKEN" != "null" ]; then
          echo "Admin token obtained"
          break
        fi
        echo "  Keycloak API not ready yet (attempt $$i)"
        sleep 10
      done

      if [ -z "$$TOKEN" ] || [ "$$TOKEN" = "null" ]; then
        echo "ERROR: Could not get Keycloak admin token"
        exit 1
      fi

      AUTH="Authorization: Bearer $$TOKEN"

      echo "Creating haven realm..."
      curl -sf -X POST "$$KC_URL/admin/realms" \
        -H "$$AUTH" -H "Content-Type: application/json" \
        -d "{\"realm\":\"haven\",\"displayName\":\"Haven Platform\",\"enabled\":true,\"registrationAllowed\":false,\"loginWithEmailAllowed\":true,\"accessTokenLifespan\":3600,\"ssoSessionIdleTimeout\":28800,\"ssoSessionMaxLifespan\":28800}" \
        || echo "  haven realm may already exist"

      echo "Creating haven-ui client..."
      curl -sf -X POST "$$KC_URL/admin/realms/haven/clients" \
        -H "$$AUTH" -H "Content-Type: application/json" \
        -d "{\"clientId\":\"haven-ui\",\"publicClient\":false,\"directAccessGrantsEnabled\":true,\"standardFlowEnabled\":true,\"redirectUris\":[\"http://localhost:3000/*\",\"http://localhost:3001/*\",\"http://app.${local._sslip_suffix}/*\",\"https://app.${local._sslip_suffix}/*\"],\"webOrigins\":[\"*\"],\"secret\":\"haven-ui-secret\"}" \
        || echo "  haven-ui client may already exist"

      echo "Creating haven-api client..."
      curl -sf -X POST "$$KC_URL/admin/realms/haven/clients" \
        -H "$$AUTH" -H "Content-Type: application/json" \
        -d "{\"clientId\":\"haven-api\",\"publicClient\":false,\"serviceAccountsEnabled\":true,\"directAccessGrantsEnabled\":true,\"secret\":\"haven-api-secret\"}" \
        || echo "  haven-api client may already exist"

      echo "Creating platform-admin role..."
      curl -sf -X POST "$$KC_URL/admin/realms/haven/roles" \
        -H "$$AUTH" -H "Content-Type: application/json" \
        -d "{\"name\":\"platform-admin\"}" \
        || echo "  platform-admin role may already exist"

      echo "Creating admin user..."
      curl -sf -X POST "$$KC_URL/admin/realms/haven/users" \
        -H "$$AUTH" -H "Content-Type: application/json" \
        -d "{\"username\":\"admin\",\"email\":\"admin@haven.dev\",\"firstName\":\"Haven\",\"lastName\":\"Admin\",\"enabled\":true,\"emailVerified\":true,\"credentials\":[{\"type\":\"password\",\"value\":\"$$ADMIN_PASS\",\"temporary\":false}]}" \
        || echo "  admin user may already exist"

      echo "Assigning platform-admin role to admin user..."
      USER_ID=$(curl -sf "$$KC_URL/admin/realms/haven/users?username=admin" \
        -H "$$AUTH" | jq -r ".[0].id" 2>/dev/null || echo "")
      ROLE_JSON=$(curl -sf "$$KC_URL/admin/realms/haven/roles/platform-admin" \
        -H "$$AUTH" 2>/dev/null || echo "")
      if [ -n "$$USER_ID" ] && [ "$$USER_ID" != "null" ] && [ -n "$$ROLE_JSON" ]; then
        curl -sf -X POST "$$KC_URL/admin/realms/haven/users/$$USER_ID/role-mappings/realm" \
          -H "$$AUTH" -H "Content-Type: application/json" \
          -d "[$$ROLE_JSON]" || echo "  role assignment may already exist"
      fi

      echo "KEYCLOAK_REALM_BOOTSTRAP_COMPLETE"
    '
  EOT
  )]

  depends_on = [helm_release.keycloak]
}

# --- 20d. Haven API + UI Secrets ---
# Creates K8s Secrets required by haven-api and haven-ui deployments.
# Depends on: haven-platform DB (for DATABASE_URL), Keycloak realm (for URLs),
# Gitea admin setup (for GITEA_ADMIN_TOKEN).
resource "ssh_resource" "haven_platform_secrets" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      # Get haven-platform DB password from CNPG-generated secret
      DB_PASS=$($K get secret haven-platform-app -n cnpg-system \
        -o jsonpath="{.data.password}" 2>/dev/null | base64 -d || echo "haven")
      DB_USER=$($K get secret haven-platform-app -n cnpg-system \
        -o jsonpath="{.data.username}" 2>/dev/null | base64 -d || echo "haven")

      # Get Gitea admin token from gitea_admin_setup
      GITEA_TOKEN=$($K get secret gitea-admin-token -n haven-system \
        -o jsonpath="{.data.token}" 2>/dev/null | base64 -d || echo "")

      DATABASE_URL="postgresql+asyncpg://$$DB_USER:$$DB_PASS@haven-platform-rw.cnpg-system.svc.cluster.local:5432/haven_platform"

      echo "Creating haven-api-secrets..."
      $K create secret generic haven-api-secrets -n haven-system \
        --from-literal=DATABASE_URL="$$DATABASE_URL" \
        --from-literal=SECRET_KEY="haven-platform-secret-$(date +%s)" \
        --from-literal=HARBOR_ADMIN_PASSWORD="${var.harbor_admin_password}" \
        --from-literal=KEYCLOAK_ADMIN_PASSWORD="${var.keycloak_admin_password}" \
        --from-literal=EVEREST_ADMIN_PASSWORD="${var.everest_admin_password}" \
        --from-literal=GITEA_ADMIN_TOKEN="$$GITEA_TOKEN" \
        --dry-run=client -o yaml | $K apply -f -

      echo "Creating haven-ui-secrets..."
      $K create secret generic haven-ui-secrets -n haven-system \
        --from-literal=NEXTAUTH_SECRET="haven-ui-nextauth-$(date +%s)" \
        --from-literal=KEYCLOAK_CLIENT_SECRET="haven-ui-secret" \
        --dry-run=client -o yaml | $K apply -f -

      echo "HAVEN_SECRETS_CREATED"
    '
  EOT
  )]

  depends_on = [
    ssh_resource.wait_haven_platform_db_ready,
    ssh_resource.keycloak_realm_bootstrap,
    ssh_resource.gitea_admin_setup,
  ]
}

# --- 20e. ArgoCD App-of-Apps Bootstrap ---
# Creates the root ArgoCD Application that discovers all other Applications
# in platform/argocd/apps/. This triggers automatic deployment of haven-api,
# haven-ui, kyverno, and kyverno-policies.
resource "ssh_resource" "argocd_app_of_apps" {
  count       = var.enable_argocd ? 1 : 0
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      echo "Creating ArgoCD app-of-apps Application..."
      cat <<APPEOF | $K apply -f -
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: haven-platform
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/NimbusProTch/InfraForge-Haven.git
    targetRevision: main
    path: platform/argocd/apps
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
APPEOF

      echo "ARGOCD_APP_OF_APPS_CREATED"
    '
  EOT
  )]

  depends_on = [
    helm_release.argocd,
    ssh_resource.haven_platform_secrets,
  ]
}

# Platform namespaces are created by namespace_security_labels (step 9b)

# --- 22. Gateway API CRDs + GatewayClass Acceptance ---
# Cilium's Gateway API support requires:
#   1. Gateway API experimental CRDs to be installed BEFORE Cilium processes them
#   2. Waiting for GatewayClass "cilium" to reach Accepted=True status
#      (not just exist — Cilium operator must reconcile it)
# Without this, haven-gateway stays in "Waiting for controller" (1970-01-01 timestamp).
resource "ssh_resource" "gateway_api" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "10m"

  commands = [
    <<-EOT
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      # Apply Gateway API experimental CRDs (includes TLSRoute, GRPCRoute, etc.)
      $K apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/experimental-install.yaml

      # Wait for Cilium operator to register the GatewayClass
      echo "Waiting for GatewayClass cilium to appear..."
      for i in $(seq 1 60); do
        if $K get gatewayclass cilium >/dev/null 2>&1; then
          echo "GatewayClass cilium found"
          break
        fi
        sleep 10
      done

      # Wait for GatewayClass to be ACCEPTED by Cilium controller.
      # This is the key step — just existing is not enough.
      # Cilium must reconcile it and set Accepted=True before creating Gateways.
      echo "Waiting for GatewayClass cilium Accepted=True..."
      for i in $(seq 1 60); do
        STATUS=$($K get gatewayclass cilium \
          -o jsonpath='{.status.conditions[?(@.type=="Accepted")].status}' 2>/dev/null || echo "")
        if [ "$STATUS" = "True" ]; then
          echo "GATEWAYCLASS_ACCEPTED"
          break
        fi
        echo "  GatewayClass status: '$STATUS' (attempt $i)"
        sleep 10
      done

      # Create gateway namespace with privileged PSA (already done by namespace_security_labels,
      # but idempotent --dry-run ensures it exists even if re-applied)
      $K create namespace haven-gateway --dry-run=client -o yaml | $K apply -f -
      $K label namespace haven-gateway \
        pod-security.kubernetes.io/enforce=privileged --overwrite
    EOT
  ]

  depends_on = [ssh_resource.namespace_security_labels]
}

# Gateway + ClusterIssuer applied via kubectl on first master
resource "ssh_resource" "gateway_resources" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = [
    <<-EOT
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      # ClusterIssuer for Let's Encrypt
      cat <<'YAML' | $K apply -f -
      apiVersion: cert-manager.io/v1
      kind: ClusterIssuer
      metadata:
        name: letsencrypt-gateway
      spec:
        acme:
          server: https://acme-v02.api.letsencrypt.org/directory
          email: admin@haven.dev
          privateKeySecretRef:
            name: letsencrypt-gateway-key
          solvers:
            - http01:
                gatewayHTTPRoute:
                  parentRefs:
                    - name: haven-gateway
                      namespace: haven-gateway
      YAML

      # Gateway resource
      cat <<'YAML' | $K apply -f -
      apiVersion: gateway.networking.k8s.io/v1
      kind: Gateway
      metadata:
        name: haven-gateway
        namespace: haven-gateway
        annotations:
          cert-manager.io/cluster-issuer: letsencrypt-gateway
      spec:
        gatewayClassName: cilium
        listeners:
          - name: http
            port: 80
            protocol: HTTP
            allowedRoutes:
              namespaces:
                from: All
          - name: https
            port: 443
            protocol: HTTPS
            tls:
              mode: Terminate
              certificateRefs:
                - name: haven-gateway-tls
            allowedRoutes:
              namespaces:
                from: All
      YAML

      # Certificate with all gateway SANs (Let's Encrypt HTTP-01)
      cat <<'YAML' | $K apply -f -
      apiVersion: cert-manager.io/v1
      kind: Certificate
      metadata:
        name: haven-gateway-tls
        namespace: haven-gateway
      spec:
        secretName: haven-gateway-tls
        issuerRef:
          name: letsencrypt-gateway
          kind: ClusterIssuer
        dnsNames:
          - harbor.${local._sslip_suffix}
          - keycloak.${local._sslip_suffix}
          - argocd.${local._sslip_suffix}
          - api.${local._sslip_suffix}
          - app.${local._sslip_suffix}
          - grafana.${local._sslip_suffix}
          - minio.${local._sslip_suffix}
          - s3.${local._sslip_suffix}
          - everest.${local._sslip_suffix}
          - gitea.${local._sslip_suffix}
          - longhorn.${local._sslip_suffix}
          - hubble.${local._sslip_suffix}
      YAML
    EOT
  ]

  depends_on = [ssh_resource.gateway_api, helm_release.cert_manager]
}

# --- 22b. Haven Proxy DaemonSet ---
# Workaround for Cilium 1.16 bug: L7LB Proxy Port is NOT propagated to
# NodePort BPF entries, so external traffic can't reach the Cilium gateway
# via NodePort. This nginx DaemonSet runs with hostNetwork:true and proxies
# to the gateway ClusterIP.
#
# Port 80  -> HTTP proxy to Cilium gateway (with large body + timeout for Harbor push)
# Port 443 -> TCP stream passthrough to Cilium gateway (TLS terminated by Cilium)
resource "ssh_resource" "haven_proxy" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = [
    <<-EOT
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      cat <<'YAML' | $K apply -f -
      apiVersion: v1
      kind: Namespace
      metadata:
        name: haven-proxy
        labels:
          pod-security.kubernetes.io/enforce: privileged
      ---
      apiVersion: v1
      kind: ConfigMap
      metadata:
        name: nginx-conf
        namespace: haven-proxy
      data:
        nginx.conf: |
          user nginx;
          worker_processes auto;
          error_log /dev/stderr warn;
          pid /tmp/nginx.pid;
          events { worker_connections 1024; }
          http {
            access_log /dev/stdout;
            client_max_body_size 2g;
            server {
              listen 80;
              location / {
                proxy_pass http://cilium-gateway-haven-gateway.haven-gateway.svc.cluster.local:80;
                proxy_http_version 1.1;
                proxy_set_header Host $host;
                proxy_set_header Connection "";
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Proto $scheme;
                proxy_connect_timeout 5s;
                proxy_read_timeout 300s;
                proxy_send_timeout 300s;
              }
            }
          }
          stream {
            server {
              listen 443;
              proxy_pass cilium-gateway-haven-gateway.haven-gateway.svc.cluster.local:443;
              proxy_connect_timeout 5s;
              proxy_timeout 300s;
            }
          }
      ---
      apiVersion: apps/v1
      kind: DaemonSet
      metadata:
        name: gateway-proxy
        namespace: haven-proxy
        labels:
          app: gateway-proxy
      spec:
        selector:
          matchLabels:
            app: gateway-proxy
        template:
          metadata:
            labels:
              app: gateway-proxy
          spec:
            hostNetwork: true
            dnsPolicy: ClusterFirstWithHostNet
            tolerations:
              - operator: "Exists"
            containers:
              - name: nginx
                image: nginx:1.27-alpine
                ports:
                  - containerPort: 80
                    hostPort: 80
                    protocol: TCP
                  - containerPort: 443
                    hostPort: 443
                    protocol: TCP
                volumeMounts:
                  - name: nginx-conf
                    mountPath: /etc/nginx/nginx.conf
                    subPath: nginx.conf
                resources:
                  requests:
                    cpu: "10m"
                    memory: "32Mi"
                  limits:
                    memory: "64Mi"
            volumes:
              - name: nginx-conf
                configMap:
                  name: nginx-conf
      YAML

      # Wait for DaemonSet to roll out
      $K rollout status daemonset/gateway-proxy -n haven-proxy --timeout=120s || true
    EOT
  ]

  depends_on = [ssh_resource.gateway_resources]
}

# --- 23. External-DNS (optional) ---
resource "helm_release" "external_dns" {
  count            = var.enable_external_dns ? 1 : 0
  name             = "external-dns"
  namespace        = "external-dns"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://kubernetes-sigs.github.io/external-dns"
  chart            = "external-dns"
  version          = var.external_dns_version
  timeout          = 600
  wait             = true

  values = [templatefile("${path.module}/helm-values/external-dns.yaml", {
    cloudflare_api_token = var.cloudflare_api_token
    domain_filters       = var.external_dns_domain_filters
  })]

  depends_on = [ssh_resource.wait_cluster_ready]
}

# --- 24. Gitea Self-Hosted Git Server (Sprint I-1) ---
# Gitea provides the haven-gitops repo that ArgoCD watches.
# Deploy chain: longhorn + cert_manager → helm_release.gitea → gitea_admin_setup → gitea_httproute
resource "helm_release" "gitea" {
  count            = var.enable_gitea ? 1 : 0
  name             = "gitea"
  namespace        = "gitea-system"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://dl.gitea.com/charts/"
  chart            = "gitea"
  version          = var.gitea_version
  timeout          = 900
  wait             = true

  values = [templatefile("${path.module}/helm-values/gitea.yaml", {
    gitea_host     = local.gitea_host
    admin_user     = var.gitea_admin_user
    admin_password = var.gitea_admin_password
    storage_size   = var.gitea_storage_size
  })]

  depends_on = [ssh_resource.wait_longhorn_ready, helm_release.cert_manager]
}

# Create haven org, haven-gitops repo, and store admin token as K8s Secret
resource "ssh_resource" "gitea_admin_setup" {
  count       = var.enable_gitea ? 1 : 0
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "10m"

  commands = [nonsensitive(<<-EOT
    bash -c '
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      echo "Waiting for Gitea pod to be ready..."
      for i in $(seq 1 60); do
        READY=$($K get pods -n gitea-system -l app.kubernetes.io/name=gitea \
          --no-headers 2>/dev/null | grep -c "1/1" || echo 0)
        if [ "$$READY" -ge "1" ]; then
          echo "GITEA_POD_READY"
          break
        fi
        echo "  Gitea not ready yet (attempt $$i)"
        sleep 10
      done

      GITEA_IP=$($K get svc gitea-http -n gitea-system -o jsonpath="{.spec.clusterIP}" 2>/dev/null || echo "")
      if [ -z "$$GITEA_IP" ]; then
        echo "ERROR: Could not get Gitea ClusterIP"
        exit 1
      fi
      GITEA_URL="http://$$GITEA_IP:3000"
      ADMIN="${var.gitea_admin_user}"
      PASS="${var.gitea_admin_password}"

      echo "Waiting for Gitea API at $$GITEA_URL..."
      for i in $(seq 1 30); do
        if curl -sf "$$GITEA_URL/api/v1/version" > /dev/null 2>&1; then
          echo "Gitea API is ready"
          break
        fi
        sleep 5
      done

      # Create haven organization (idempotent)
      curl -sf -X POST "$$GITEA_URL/api/v1/orgs" \
        -H "Content-Type: application/json" \
        -u "$$ADMIN:$$PASS" \
        -d "{\"username\":\"haven\",\"visibility\":\"private\",\"repo_admin_change_team_access\":true}" \
        || echo "Org 'haven' may already exist"

      # Create haven-gitops repository (idempotent — auto_init adds README on main branch)
      curl -sf -X POST "$$GITEA_URL/api/v1/orgs/haven/repos" \
        -H "Content-Type: application/json" \
        -u "$$ADMIN:$$PASS" \
        -d "{\"name\":\"haven-gitops\",\"private\":true,\"auto_init\":true,\"default_branch\":\"main\",\"description\":\"Haven Platform GitOps manifests\"}" \
        || echo "Repo 'haven-gitops' may already exist"

      # Delete existing token if present, then create a fresh one
      curl -sf -X DELETE "$$GITEA_URL/api/v1/users/$$ADMIN/tokens/haven-platform-token" \
        -u "$$ADMIN:$$PASS" || true

      TOKEN=$(curl -sf -X POST "$$GITEA_URL/api/v1/users/$$ADMIN/tokens" \
        -H "Content-Type: application/json" \
        -u "$$ADMIN:$$PASS" \
        -d "{\"name\":\"haven-platform-token\"}" | jq -r ".sha1")

      if [ -z "$$TOKEN" ] || [ "$$TOKEN" = "null" ]; then
        echo "ERROR: Failed to generate Gitea admin token"
        exit 1
      fi

      # Store token as K8s Secret in haven-system
      $K create secret generic gitea-admin-token \
        -n haven-system \
        --from-literal=token="$$TOKEN" \
        --from-literal=username="$$ADMIN" \
        --from-literal=gitea_url="http://gitea-http.gitea-system.svc.cluster.local:3000" \
        --dry-run=client -o yaml | $K apply -f -

      echo "GITEA_SETUP_COMPLETE: haven org + haven-gitops repo created, token stored"
    '
  EOT
  )]

  depends_on = [helm_release.gitea]
}

# HTTPRoute: gitea.<LB_IP>.sslip.io → gitea-http:3000
resource "ssh_resource" "gitea_httproute" {
  count       = var.enable_gitea ? 1 : 0
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = [
    <<-EOT
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl
      cat <<'YAML' | $K apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: gitea
  namespace: gitea-system
spec:
  parentRefs:
    - name: haven-gateway
      namespace: haven-gateway
  hostnames:
    - "${local.gitea_host}"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: gitea-http
          port: 3000
YAML
    EOT
  ]

  depends_on = [ssh_resource.gitea_admin_setup, ssh_resource.gateway_resources]
}

# ============================================================
# CI Runner — Self-hosted GitHub Actions runner (Hetzner CX22)
# ============================================================
# Dedicated VPS for CI/CD pipelines. Benefits:
#   - No GitHub Actions minute limits
#   - No runner allocation failures (dedicated)
#   - EU data sovereignty (code never leaves Hetzner)
#   - Faster builds (no queue wait)
# Cost: €4.49/month (CX22: 2 vCPU, 4GB RAM, 40GB SSD)

resource "hcloud_server" "ci_runner" {
  count       = var.enable_ci_runner ? 1 : 0
  name        = "haven-ci-runner-${var.environment}"
  server_type = var.ci_runner_server_type
  image       = var.os_image
  location    = var.location_primary
  ssh_keys    = [module.hetzner_infra.ssh_key_id]

  user_data = <<-CLOUD_INIT
    #!/bin/bash
    set -euo pipefail

    # System packages for CI (docker, git, node, python)
    apt-get update -qq
    apt-get install -y -qq \
      curl git jq unzip docker.io python3 python3-pip python3-venv \
      nodejs npm build-essential

    systemctl enable --now docker

    # Create runner user
    useradd -m -s /bin/bash -G docker runner

    # Install GitHub Actions runner
    RUNNER_VERSION="2.321.0"
    cd /home/runner
    mkdir -p actions-runner && cd actions-runner
    curl -sL "https://github.com/actions/runner/releases/download/v$${RUNNER_VERSION}/actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz" | tar xz
    chown -R runner:runner /home/runner/actions-runner

    # Runner will be configured manually after provisioning:
    #   ssh runner@<ip>
    #   cd actions-runner
    #   ./config.sh --url https://github.com/NimbusProTch/InfraForge-Haven \
    #     --token <GITHUB_RUNNER_TOKEN> --name haven-ci-runner --labels self-hosted,haven
    #   sudo ./svc.sh install runner
    #   sudo ./svc.sh start
  CLOUD_INIT

  labels = {
    role        = "ci-runner"
    environment = var.environment
    project     = "haven"
  }
}

output "ci_runner_ip" {
  description = "CI runner public IP (SSH: ssh runner@<ip>)"
  value       = var.enable_ci_runner ? hcloud_server.ci_runner[0].ipv4_address : null
}
