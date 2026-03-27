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

  # Multi-AZ distribution: first 2 nodes primary, rest secondary
  master_locations = [for i in range(var.master_count) : i < 2 ? var.location_primary : var.location_secondary]
  worker_locations = [for i in range(var.worker_count) : i < 2 ? var.location_primary : var.location_secondary]

  # First master gets a static private IP for other nodes to join
  first_master_private_ip = "10.0.1.10"

  # sslip.io hostnames (replaced by External-DNS + real domain in production)
  lb_dns = module.hetzner_infra.load_balancer_ip
  harbor_host    = "harbor.${local.lb_dns}.sslip.io"
  argocd_host    = "argocd.${local.lb_dns}.sslip.io"
  keycloak_host  = "keycloak.${local.lb_dns}.sslip.io"
  api_host       = "api.${local.lb_dns}.sslip.io"
  ui_host        = "ui.${local.lb_dns}.sslip.io"
  minio_host     = "minio.${local.lb_dns}.sslip.io"
  s3_host        = "s3.${local.lb_dns}.sslip.io"
  everest_host   = "everest.${local.lb_dns}.sslip.io"
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
}

# --- 3. RKE2 Cluster Config (cloud-init generation) ---
module "rke2_cluster" {
  source = "../../modules/rke2-cluster"

  cluster_name            = var.cluster_name
  kubernetes_version      = var.kubernetes_version
  cluster_token           = random_password.cluster_token.result
  first_master_private_ip = local.first_master_private_ip
  lb_ip                   = module.hetzner_infra.load_balancer_ip
  enable_hubble           = true
  cilium_operator_replicas = 1
  disable_kube_proxy      = true
  enable_cis_profile      = true
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
    tolerations:
      - operator: Exists
CILEOF

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
RKEEOF

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
      for NS in longhorn-system cert-manager monitoring logging harbor-system minio-system \
                argocd everest-system redis-system rabbitmq-system keycloak \
                haven-system haven-builds haven-gateway; do
        $K create namespace $NS --dry-run=client -o yaml | $K apply -f -
        $K label namespace $NS \
          pod-security.kubernetes.io/enforce=privileged \
          pod-security.kubernetes.io/audit=privileged \
          pod-security.kubernetes.io/warn=privileged \
          --overwrite
      done
      echo "All system namespaces labeled privileged"
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

  depends_on = [helm_release.longhorn]
}

# --- 12. Kube-Prometheus-Stack (Haven Check #14: Monitoring) ---
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
    storage_class = "longhorn"
  })]

  depends_on = [helm_release.longhorn]
}

# --- 13. Logging (Haven Check #13: Log Aggregation) ---
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

  depends_on = [helm_release.longhorn]
}

# --- 14. Harbor Image Registry ---
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

  depends_on = [helm_release.longhorn, helm_release.cert_manager]
}

# --- 15. MinIO Object Storage ---
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
    root_user     = var.minio_root_user
    root_password = var.minio_root_password
    storage_size  = var.minio_storage_size
  })]

  depends_on = [helm_release.longhorn]
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

# --- 17. Percona Everest (Database Platform) ---
# Installs Percona Everest operator + UI for PostgreSQL, MySQL, MongoDB
resource "helm_release" "everest_operator" {
  count            = var.enable_everest ? 1 : 0
  name             = "everest-operator"
  namespace        = "everest-system"
  create_namespace = false  # Created by namespace_security_labels
  repository       = "https://percona.github.io/percona-helm-charts"
  chart            = "everest-operator"
  version          = var.everest_operator_version
  timeout          = 900
  wait             = true

  depends_on = [ssh_resource.namespace_security_labels, helm_release.longhorn]
}

# Percona Everest server (UI + API)
resource "helm_release" "everest" {
  count            = var.enable_everest ? 1 : 0
  name             = "everest"
  namespace        = "everest-system"
  create_namespace = false
  repository       = "https://percona.github.io/percona-helm-charts"
  chart            = "everest"
  version          = var.everest_version
  timeout          = 600
  wait             = true

  depends_on = [helm_release.everest_operator]
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

# --- 20. Keycloak (Production mode + CNPG PostgreSQL) ---
# First create the Keycloak database via CNPG
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

  depends_on = [helm_release.longhorn, helm_release.everest]
}

resource "helm_release" "keycloak" {
  count            = var.enable_keycloak ? 1 : 0
  name             = "keycloak"
  namespace        = "keycloak"
  create_namespace = false
  repository       = "https://codecentric.github.io/helm-charts"
  chart            = "keycloakx"
  version          = var.keycloak_chart_version
  timeout          = 600
  wait             = true

  values = [templatefile("${path.module}/helm-values/keycloak.yaml", {
    keycloak_host     = local.keycloak_host
    admin_password    = var.keycloak_admin_password
    db_secret_name    = "keycloak-db-app"
  })]

  depends_on = [helm_release.keycloak_db]
}

# Platform namespaces are created by namespace_security_labels (step 9b)

# --- 22. Gateway API Resources ---
# Applied after Cilium is running and cert-manager is installed
resource "ssh_resource" "gateway_api" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = [
    <<-EOT
      export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
      K=/var/lib/rancher/rke2/bin/kubectl

      # Create gateway namespace
      $K create namespace haven-gateway --dry-run=client -o yaml | $K apply -f -

      # Apply Gateway API experimental CRDs
      $K apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/experimental-install.yaml 2>/dev/null || true

      # Wait for Cilium GatewayClass
      for i in $(seq 1 30); do
        if $K get gatewayclass cilium >/dev/null 2>&1; then
          echo "GatewayClass cilium found"
          break
        fi
        sleep 10
      done
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
    EOT
  ]

  depends_on = [ssh_resource.gateway_api, helm_release.cert_manager]
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
