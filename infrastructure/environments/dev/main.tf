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

  # First master bootstraps, others join
  user_data = count.index == 0 ? module.rke2_cluster.first_master_cloud_init : module.rke2_cluster.joining_master_cloud_init

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

  user_data = module.rke2_cluster.worker_cloud_init

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

# --- 7. Retrieve Kubeconfig from First Master ---
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

  depends_on = [
    hcloud_server.master,
    hcloud_server_network.master,
  ]
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
    hcloud_server.worker,
    hcloud_server_network.worker,
    hcloud_load_balancer_target.master,
    hcloud_load_balancer_target.worker,
  ]
}

# --- 9. Node Topology Labels (Haven Check #1: Multi-AZ) ---
resource "ssh_resource" "node_topology_labels" {
  host        = hcloud_server.master[0].ipv4_address
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = concat(
    ["export KUBECONFIG=/etc/rancher/rke2/rke2.yaml && export PATH=$PATH:/var/lib/rancher/rke2/bin"],
    [for i in range(var.master_count) :
      "kubectl label node haven-master-${var.environment}-${i + 1} topology.kubernetes.io/zone=${local.master_locations[i]} topology.kubernetes.io/region=eu --overwrite"
    ],
    [for i in range(var.worker_count) :
      "kubectl label node haven-worker-${var.environment}-${i + 1} topology.kubernetes.io/zone=${local.worker_locations[i]} topology.kubernetes.io/region=eu --overwrite"
    ]
  )

  depends_on = [ssh_resource.wait_cluster_ready]
}

# ============================================================
# Platform Operators (via Helm provider)
# ============================================================

# --- 10. Longhorn Storage (Haven Check #10: RWX) ---
resource "helm_release" "longhorn" {
  count            = var.enable_longhorn ? 1 : 0
  name             = "longhorn"
  namespace        = "longhorn-system"
  create_namespace = true
  repository       = "https://charts.longhorn.io"
  chart            = "longhorn"
  version          = var.longhorn_version
  timeout          = 900
  wait             = true

  values = [templatefile("${path.module}/helm-values/longhorn.yaml", {
    replica_count = var.worker_count >= 3 ? 3 : var.worker_count
  })]

  depends_on = [ssh_resource.wait_cluster_ready]
}

# --- 11. Cert-Manager (Haven Check #12: Auto HTTPS) ---
resource "helm_release" "cert_manager" {
  count            = var.enable_cert_manager ? 1 : 0
  name             = "cert-manager"
  namespace        = "cert-manager"
  create_namespace = true
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
  create_namespace = true
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
  create_namespace = true
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
  create_namespace = true
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
  create_namespace = true
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
  create_namespace = true
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
  create_namespace = true
  repository       = "https://percona.github.io/percona-helm-charts"
  chart            = "everest-operator"
  version          = var.everest_operator_version
  timeout          = 900
  wait             = true

  depends_on = [helm_release.longhorn]
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
  create_namespace = true
  repository       = "https://ot-container-kit.github.io/helm-charts"
  chart            = "redis-operator"
  version          = var.redis_operator_version
  timeout          = 600
  wait             = true

  depends_on = [ssh_resource.wait_cluster_ready]
}

# --- 19. RabbitMQ Cluster Operator ---
resource "helm_release" "rabbitmq_operator" {
  count            = var.enable_rabbitmq_operator ? 1 : 0
  name             = "rabbitmq-cluster-operator"
  namespace        = "rabbitmq-system"
  create_namespace = true
  repository       = "https://charts.bitnami.com/bitnami"
  chart            = "rabbitmq-cluster-operator"
  version          = var.rabbitmq_operator_version
  timeout          = 600
  wait             = true

  depends_on = [ssh_resource.wait_cluster_ready]
}

# --- 20. Keycloak (Production mode + CNPG PostgreSQL) ---
# First create the Keycloak database via CNPG
resource "helm_release" "keycloak_db" {
  count            = var.enable_keycloak ? 1 : 0
  name             = "keycloak-db"
  namespace        = "keycloak"
  create_namespace = true
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

  depends_on = [helm_release.longhorn, helm_release.everest_operator]
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

# --- 21. Platform Namespaces ---
resource "kubernetes_namespace" "haven_system" {
  metadata {
    name = "haven-system"
    labels = {
      project     = "haven"
      environment = var.environment
    }
  }
  depends_on = [ssh_resource.wait_cluster_ready]
}

resource "kubernetes_namespace" "haven_builds" {
  metadata {
    name = "haven-builds"
    labels = {
      project     = "haven"
      environment = var.environment
    }
  }
  depends_on = [ssh_resource.wait_cluster_ready]
}

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
      export PATH=$PATH:/var/lib/rancher/rke2/bin

      # Create gateway namespace
      kubectl create namespace haven-gateway --dry-run=client -o yaml | kubectl apply -f -

      # Apply Gateway API experimental CRDs (for TLSRoute support)
      kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/experimental-install.yaml 2>/dev/null || true

      # Wait for Cilium GatewayClass
      for i in $(seq 1 30); do
        if kubectl get gatewayclass cilium >/dev/null 2>&1; then
          echo "GatewayClass cilium found"
          break
        fi
        sleep 10
      done
    EOT
  ]

  depends_on = [ssh_resource.wait_cluster_ready, helm_release.cert_manager]
}

# ClusterIssuer for Let's Encrypt
resource "kubernetes_manifest" "letsencrypt_issuer" {
  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "ClusterIssuer"
    metadata = {
      name = "letsencrypt-gateway"
    }
    spec = {
      acme = {
        server = "https://acme-v02.api.letsencrypt.org/directory"
        email  = "admin@haven.dev"
        privateKeySecretRef = {
          name = "letsencrypt-gateway-key"
        }
        solvers = [{
          http01 = {
            gatewayHTTPRoute = {
              parentRefs = [{
                name      = "haven-gateway"
                namespace = "haven-gateway"
              }]
            }
          }
        }]
      }
    }
  }

  depends_on = [helm_release.cert_manager, ssh_resource.gateway_api]
}

# Gateway resource
resource "kubernetes_manifest" "haven_gateway" {
  manifest = {
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "Gateway"
    metadata = {
      name      = "haven-gateway"
      namespace = "haven-gateway"
      annotations = {
        "cert-manager.io/cluster-issuer" = "letsencrypt-gateway"
      }
    }
    spec = {
      gatewayClassName = "cilium"
      listeners = [
        {
          name     = "http"
          port     = 80
          protocol = "HTTP"
          allowedRoutes = {
            namespaces = { from = "All" }
          }
        },
        {
          name     = "https"
          port     = 443
          protocol = "HTTPS"
          tls = {
            mode = "Terminate"
            certificateRefs = [{
              name = "haven-gateway-tls"
            }]
          }
          allowedRoutes = {
            namespaces = { from = "All" }
          }
        }
      ]
    }
  }

  depends_on = [ssh_resource.gateway_api]
}

# --- 23. External-DNS (optional) ---
resource "helm_release" "external_dns" {
  count            = var.enable_external_dns ? 1 : 0
  name             = "external-dns"
  namespace        = "external-dns"
  create_namespace = true
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
