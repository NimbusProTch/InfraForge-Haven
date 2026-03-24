# ============================================================
# Haven Platform - Dev Environment (Hetzner Cloud)
# ============================================================
# Following Rancher official quickstart pattern:
#   1. Hetzner base infra (network, firewall, SSH, LB, mgmt node)
#   2. SSH: Install K3s on management node
#   3. SSH: Retrieve kubeconfig
#   4. Helm: Install cert-manager + Rancher
#   5. Bootstrap Rancher (rancher2 provider - Go native)
#   6. RKE2 cluster with Cilium CNI (via rancher-cluster module)
#   7. Master/Worker nodes (Rancher insecure_node_command)
#   8. Wait for cluster active (rancher2_cluster_sync)
#   9. Apps: Longhorn, Cert-Manager, Monitoring, Logging
# ============================================================

locals {
  node_username      = "root"
  rancher_server_dns = join(".", ["rancher", module.hetzner_infra.management_ip, "sslip.io"])

  # Multi-AZ distribution: first 2 nodes primary, rest secondary
  master_locations = [for i in range(var.master_count) : i < 2 ? var.location_primary : var.location_secondary]
  worker_locations = [for i in range(var.worker_count) : i < 2 ? var.location_primary : var.location_secondary]
}

# --- 1. SSH Key (generated, like official quickstart) ---
resource "tls_private_key" "global_key" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "local_sensitive_file" "ssh_private_key_pem" {
  filename        = "${path.module}/id_rsa"
  content         = tls_private_key.global_key.private_key_pem
  file_permission = "0600"
}

# --- 2. Base Infrastructure ---
module "hetzner_infra" {
  source = "../../modules/hetzner-infra"

  environment            = var.environment
  location_primary       = var.location_primary
  location_secondary     = var.location_secondary
  management_server_type = var.management_server_type
  ssh_public_key         = tls_private_key.global_key.public_key_openssh
  network_cidr           = var.network_cidr
  subnet_cidr            = var.subnet_cidr
}

# --- 3. Install K3s via SSH (official pattern) ---
resource "ssh_resource" "install_k3s" {
  host = module.hetzner_infra.management_ip
  commands = [
    "bash -c 'curl https://get.k3s.io | INSTALL_K3S_EXEC=\"server --node-external-ip ${module.hetzner_infra.management_ip}\" INSTALL_K3S_VERSION=${var.k3s_version} sh -'"
  ]
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
}

# --- 4. Install cert-manager + Rancher via SSH (remote Helm) ---
# Uses Helm on the management node itself - no local port 6443 access needed
resource "ssh_resource" "install_cert_manager" {
  depends_on = [ssh_resource.install_k3s]
  host       = module.hetzner_infra.management_ip
  commands = [
    <<-EOT
      bash -c '
        export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

        # Wait for K3s API to be ready
        echo "Waiting for K3s API..."
        for i in $(seq 1 60); do
          if kubectl get nodes >/dev/null 2>&1; then
            echo "K3s API ready!"
            break
          fi
          echo "Attempt $i/60..."
          sleep 5
        done

        # Install Helm if not present
        if ! command -v helm &>/dev/null; then
          echo "Installing Helm..."
          curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
        fi

        # Add Jetstack repo and install cert-manager
        helm repo add jetstack https://charts.jetstack.io
        helm repo update jetstack
        helm upgrade --install cert-manager jetstack/cert-manager \
          --namespace cert-manager --create-namespace \
          --version ${var.cert_manager_version} \
          --set installCRDs=true \
          --wait --timeout 5m

        echo "cert-manager installed successfully"
      '
    EOT
  ]
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "10m"
}

# --- 5. Install Rancher via SSH (remote Helm) ---
resource "ssh_resource" "install_rancher" {
  depends_on = [ssh_resource.install_cert_manager]
  host       = module.hetzner_infra.management_ip
  commands = [
    <<-EOT
      bash -c '
        export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

        # Add Rancher repo and install
        helm repo add rancher-stable ${var.rancher_helm_repository}
        helm repo update rancher-stable
        helm upgrade --install rancher rancher-stable/rancher \
          --namespace cattle-system --create-namespace \
          --version ${var.rancher_chart_version} \
          --set hostname=${local.rancher_server_dns} \
          --set replicas=1 \
          --set bootstrapPassword=${var.rancher_bootstrap_password} \
          --wait --timeout 10m

        echo "Rancher installed successfully"
      '
    EOT
  ]
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "15m"
}

# --- 6. Bootstrap Rancher (Go native) ---
resource "rancher2_bootstrap" "admin" {
  depends_on = [ssh_resource.install_rancher]
  provider   = rancher2.bootstrap

  initial_password = var.rancher_bootstrap_password
  password         = var.rancher_admin_password
}

# --- 7. RKE2 Cluster (module: Cilium CNI + templates) ---
module "rancher_cluster" {
  source = "../../modules/rancher-cluster"
  providers = {
    rancher2 = rancher2.admin
  }

  cluster_name       = var.cluster_name
  kubernetes_version = var.kubernetes_version

  # Cilium CNI settings
  enable_hubble            = true
  cilium_operator_replicas = 1
  disable_kube_proxy       = true

  # Longhorn values (rendered by module, used below)
  longhorn_replica_count = var.worker_count >= 3 ? 3 : var.worker_count

  # Harbor
  harbor_host                  = join(".", ["harbor", module.hetzner_infra.load_balancer_ip, "sslip.io"])
  harbor_admin_password        = var.harbor_admin_password
  harbor_registry_storage_size = var.harbor_registry_storage_size

  # MinIO
  minio_root_user     = var.minio_root_user
  minio_root_password = var.minio_root_password
  minio_storage_size  = var.minio_storage_size
  minio_console_host  = join(".", ["minio", module.hetzner_infra.load_balancer_ip, "sslip.io"])
  minio_api_host      = join(".", ["s3", module.hetzner_infra.load_balancer_ip, "sslip.io"])

  # ArgoCD
  argocd_host = join(".", ["argocd", module.hetzner_infra.load_balancer_ip, "sslip.io"])

  # Keycloak
  keycloak_host           = join(".", ["keycloak", module.hetzner_infra.load_balancer_ip, "sslip.io"])
  keycloak_admin_password = var.keycloak_admin_password
  keycloak_db_password    = var.keycloak_db_password

  # External-DNS
  external_dns_cloudflare_token = var.cloudflare_api_token
  external_dns_domain_filters   = var.external_dns_domain_filters
}

# --- 9. Master Nodes (Rancher insecure_node_command) ---
resource "hcloud_server" "master" {
  count        = var.master_count
  name         = "haven-master-${var.environment}-${count.index + 1}"
  server_type  = var.master_server_type
  image        = var.os_image
  location     = local.master_locations[count.index]
  ssh_keys     = [module.hetzner_infra.ssh_key_id]
  firewall_ids = [module.hetzner_infra.firewall_id]

  user_data = templatefile("${path.module}/templates/node-cloud-init.yaml.tpl", {
    register_command = nonsensitive(module.rancher_cluster.insecure_node_command)
    node_roles       = "--etcd --controlplane"
  })

  labels = {
    role        = "master"
    environment = var.environment
    project     = "haven"
    node_index  = tostring(count.index + 1)
  }
}

resource "hcloud_server_network" "master" {
  count     = var.master_count
  server_id = hcloud_server.master[count.index].id
  subnet_id = module.hetzner_infra.subnet_id
}

# --- 10. Worker Nodes (Rancher insecure_node_command) ---
resource "hcloud_server" "worker" {
  count        = var.worker_count
  name         = "haven-worker-${var.environment}-${count.index + 1}"
  server_type  = var.worker_server_type
  image        = var.os_image
  location     = local.worker_locations[count.index]
  ssh_keys     = [module.hetzner_infra.ssh_key_id]
  firewall_ids = [module.hetzner_infra.firewall_id]

  user_data = templatefile("${path.module}/templates/node-cloud-init.yaml.tpl", {
    register_command = nonsensitive(module.rancher_cluster.insecure_node_command)
    node_roles       = "--worker"
  })

  labels = {
    role        = "worker"
    environment = var.environment
    project     = "haven"
    node_index  = tostring(count.index + 1)
  }
}

resource "hcloud_server_network" "worker" {
  count     = var.worker_count
  server_id = hcloud_server.worker[count.index].id
  subnet_id = module.hetzner_infra.subnet_id
}

# --- 11. Load Balancer Targets (master + worker nodes via private network) ---
# use_private_ip = true: LB reaches nodes via private network, bypassing Hetzner firewall.
# This allows NodePort 30080/30443 to be reached without opening them in the public firewall.
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

# --- 12. Wait for Cluster Active (native rancher2_cluster_sync) ---
resource "rancher2_cluster_sync" "cluster" {
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  wait_catalogs = true
  state_confirm = 3

  timeouts {
    create = "45m"
    update = "45m"
  }

  depends_on = [
    hcloud_server.master,
    hcloud_server.worker,
    hcloud_server_network.master,
    hcloud_server_network.worker,
  ]
}

# --- 13. Longhorn Storage (via Rancher marketplace) ---
resource "rancher2_app_v2" "longhorn" {
  count         = var.enable_longhorn ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "longhorn"
  namespace     = "longhorn-system"
  repo_name     = "rancher-charts"
  chart_name    = "longhorn"
  chart_version = var.longhorn_version

  values = module.rancher_cluster.longhorn_values

  timeouts {
    create = "15m"
    update = "15m"
    delete = "10m"
  }

  depends_on = [rancher2_cluster_sync.cluster]
}

# --- 14. Cert-Manager on workload cluster (Haven Check #12) ---
resource "rancher2_catalog_v2" "jetstack" {
  count      = var.enable_cert_manager ? 1 : 0
  provider   = rancher2.admin
  cluster_id = module.rancher_cluster.cluster_id
  name       = "jetstack"
  url        = "https://charts.jetstack.io"

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "cert_manager" {
  count         = var.enable_cert_manager ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "cert-manager"
  namespace     = "cert-manager"
  repo_name     = "jetstack"
  chart_name    = "cert-manager"
  chart_version = var.cert_manager_version

  values = module.rancher_cluster.cert_manager_values

  timeouts {
    create = "10m"
    update = "10m"
    delete = "10m"
  }

  depends_on = [rancher2_catalog_v2.jetstack, rancher2_app_v2.longhorn]
}

# --- 15. Rancher Monitoring (Haven Check #14) ---
resource "rancher2_app_v2" "monitoring_crd" {
  count         = var.enable_monitoring ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "rancher-monitoring-crd"
  namespace     = "cattle-monitoring-system"
  repo_name     = "rancher-charts"
  chart_name    = "rancher-monitoring-crd"
  chart_version = var.monitoring_version

  timeouts {
    create = "10m"
    update = "10m"
    delete = "10m"
  }

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "monitoring" {
  count         = var.enable_monitoring ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "rancher-monitoring"
  namespace     = "cattle-monitoring-system"
  repo_name     = "rancher-charts"
  chart_name    = "rancher-monitoring"
  chart_version = var.monitoring_version

  values = module.rancher_cluster.monitoring_values

  timeouts {
    create = "15m"
    update = "15m"
    delete = "15m"
  }

  depends_on = [rancher2_app_v2.monitoring_crd, rancher2_app_v2.longhorn]
}

# --- 16. Rancher Logging (Haven Check #13) ---
resource "rancher2_app_v2" "logging_crd" {
  count         = var.enable_logging ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "rancher-logging-crd"
  namespace     = "cattle-logging-system"
  repo_name     = "rancher-charts"
  chart_name    = "rancher-logging-crd"
  chart_version = var.logging_version

  timeouts {
    create = "10m"
    update = "10m"
    delete = "10m"
  }

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "logging" {
  count         = var.enable_logging ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "rancher-logging"
  namespace     = "cattle-logging-system"
  repo_name     = "rancher-charts"
  chart_name    = "rancher-logging"
  chart_version = var.logging_version

  values = module.rancher_cluster.logging_values

  timeouts {
    create = "15m"
    update = "15m"
    delete = "15m"
  }

  depends_on = [rancher2_app_v2.logging_crd, rancher2_app_v2.longhorn]
}

# --- 17. Harbor Image Registry ---
resource "rancher2_catalog_v2" "harbor" {
  count      = var.enable_harbor ? 1 : 0
  provider   = rancher2.admin
  cluster_id = module.rancher_cluster.cluster_id
  name       = "harbor"
  url        = "https://helm.goharbor.io"

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "harbor" {
  count         = var.enable_harbor ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "harbor"
  namespace     = "harbor-system"
  repo_name     = "harbor"
  chart_name    = "harbor"
  chart_version = var.harbor_version

  values = module.rancher_cluster.harbor_values

  timeouts {
    create = "25m"
    update = "15m"
    delete = "20m"
  }

  depends_on = [rancher2_catalog_v2.harbor, rancher2_app_v2.longhorn, rancher2_app_v2.cert_manager]
}

# --- 18. MinIO Object Storage ---
resource "rancher2_catalog_v2" "minio" {
  count      = var.enable_minio ? 1 : 0
  provider   = rancher2.admin
  cluster_id = module.rancher_cluster.cluster_id
  name       = "minio"
  url        = "https://charts.min.io"

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "minio" {
  count         = var.enable_minio ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "minio"
  namespace     = "minio-system"
  repo_name     = "minio"
  chart_name    = "minio"
  chart_version = var.minio_version

  values = module.rancher_cluster.minio_values

  timeouts {
    create = "25m"
    update = "15m"
    delete = "20m"
  }

  depends_on = [rancher2_catalog_v2.minio, rancher2_app_v2.longhorn]
}

# --- 19. CloudNativePG Operator ---
resource "rancher2_catalog_v2" "cnpg" {
  count      = var.enable_cnpg ? 1 : 0
  provider   = rancher2.admin
  cluster_id = module.rancher_cluster.cluster_id
  name       = "cnpg"
  url        = "https://cloudnative-pg.github.io/charts"

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "cnpg" {
  count         = var.enable_cnpg ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "cloudnative-pg"
  namespace     = "cnpg-system"
  repo_name     = "cnpg"
  chart_name    = "cloudnative-pg"
  chart_version = var.cnpg_version

  values = module.rancher_cluster.cnpg_values

  timeouts {
    create = "10m"
    update = "10m"
    delete = "10m"
  }

  depends_on = [rancher2_catalog_v2.cnpg, rancher2_app_v2.longhorn]
}

# --- 20. ArgoCD ---
resource "rancher2_catalog_v2" "argocd" {
  count      = var.enable_argocd ? 1 : 0
  provider   = rancher2.admin
  cluster_id = module.rancher_cluster.cluster_id
  name       = "argo"
  url        = "https://argoproj.github.io/argo-helm"

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "argocd" {
  count         = var.enable_argocd ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "argocd"
  namespace     = "argocd"
  repo_name     = "argo"
  chart_name    = "argo-cd"
  chart_version = var.argocd_version

  values = module.rancher_cluster.argocd_values

  timeouts {
    create = "15m"
    update = "15m"
    delete = "10m"
  }

  depends_on = [rancher2_catalog_v2.argocd, rancher2_app_v2.cert_manager]
}

# --- 21. Keycloak ---
# NOTE: Bitnami Keycloak images removed from all public registries (Docker Hub, registry.bitnami.com).
# Using official quay.io/keycloak/keycloak image via kubectl apply (ssh_resource).
# Sprint 1: dev mode (H2 in-memory). Sprint 2: migrate to CNPG PostgreSQL.
#
# rancher2_catalog_v2.bitnami kept so existing state entry is not destroyed.
resource "rancher2_catalog_v2" "bitnami" {
  count      = var.enable_keycloak ? 1 : 0
  provider   = rancher2.admin
  cluster_id = module.rancher_cluster.cluster_id
  name       = "bitnami"
  url        = "https://charts.bitnami.com/bitnami"

  depends_on = [rancher2_cluster_sync.cluster]
}

locals {
  keycloak_manifest_yaml = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: keycloak-admin
      namespace: keycloak
    type: Opaque
    stringData:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: "${var.keycloak_admin_password}"
    ---
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: keycloak
      namespace: keycloak
      labels:
        app: keycloak
    spec:
      replicas: 1
      selector:
        matchLabels:
          app: keycloak
      template:
        metadata:
          labels:
            app: keycloak
        spec:
          containers:
            - name: keycloak
              image: quay.io/keycloak/keycloak:26.1
              args: ["start-dev"]
              env:
                - name: KEYCLOAK_ADMIN
                  valueFrom:
                    secretKeyRef:
                      name: keycloak-admin
                      key: KEYCLOAK_ADMIN
                - name: KEYCLOAK_ADMIN_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: keycloak-admin
                      key: KEYCLOAK_ADMIN_PASSWORD
                - name: KC_PROXY_HEADERS
                  value: "xforwarded"
                - name: KC_HOSTNAME_STRICT
                  value: "false"
                - name: KC_HTTP_ENABLED
                  value: "true"
              ports:
                - name: http
                  containerPort: 8080
              readinessProbe:
                tcpSocket:
                  port: 8080
                initialDelaySeconds: 30
                periodSeconds: 10
                failureThreshold: 6
              resources:
                requests:
                  cpu: "500m"
                  memory: "512Mi"
                limits:
                  memory: "1Gi"
          tolerations:
            - operator: "Exists"
    ---
    apiVersion: v1
    kind: Service
    metadata:
      name: keycloak
      namespace: keycloak
    spec:
      selector:
        app: keycloak
      ports:
        - name: http
          port: 80
          targetPort: 8080
      type: ClusterIP
  YAML
}

resource "ssh_resource" "keycloak" {
  count       = var.enable_keycloak ? 1 : 0
  host        = module.hetzner_infra.management_ip
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = [
    "kubectl get secret -n fleet-default ${var.cluster_name}-kubeconfig -o jsonpath='{.data.value}' | base64 -d > /tmp/workload-kubeconfig",
    # Delete existing Service first to avoid stale selector from old Bitnami install
    "KUBECONFIG=/tmp/workload-kubeconfig kubectl delete svc keycloak -n keycloak --ignore-not-found",
    "echo '${base64encode(local.keycloak_manifest_yaml)}' | base64 -d | KUBECONFIG=/tmp/workload-kubeconfig kubectl apply -f -",
  ]

  depends_on = [rancher2_cluster_sync.cluster]
}

# --- 22. External-DNS (optional, requires cloudflare_api_token) ---
resource "rancher2_catalog_v2" "external_dns" {
  count      = var.enable_external_dns ? 1 : 0
  provider   = rancher2.admin
  cluster_id = module.rancher_cluster.cluster_id
  name       = "external-dns"
  url        = "https://kubernetes-sigs.github.io/external-dns"

  depends_on = [rancher2_cluster_sync.cluster]
}

resource "rancher2_app_v2" "external_dns" {
  count         = var.enable_external_dns ? 1 : 0
  provider      = rancher2.admin
  cluster_id    = module.rancher_cluster.cluster_id
  name          = "external-dns"
  namespace     = "external-dns"
  repo_name     = "external-dns"
  chart_name    = "external-dns"
  chart_version = var.external_dns_version

  values = module.rancher_cluster.external_dns_values

  timeouts {
    create = "10m"
    update = "10m"
    delete = "10m"
  }

  depends_on = [rancher2_catalog_v2.external_dns, rancher2_cluster_sync.cluster]
}

# --- 23. Platform Namespaces (haven-system, haven-builds) ---
resource "ssh_resource" "platform_namespaces" {
  host        = module.hetzner_infra.management_ip
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = [
    "kubectl get secret -n fleet-default ${var.cluster_name}-kubeconfig -o jsonpath='{.data.value}' | base64 -d > /tmp/workload-kubeconfig",
    "KUBECONFIG=/tmp/workload-kubeconfig kubectl create namespace haven-system --dry-run=client -o yaml | KUBECONFIG=/tmp/workload-kubeconfig kubectl apply -f -",
    "KUBECONFIG=/tmp/workload-kubeconfig kubectl create namespace haven-builds --dry-run=client -o yaml | KUBECONFIG=/tmp/workload-kubeconfig kubectl apply -f -",
    "KUBECONFIG=/tmp/workload-kubeconfig kubectl label namespace haven-system project=haven environment=${var.environment} --overwrite",
    "KUBECONFIG=/tmp/workload-kubeconfig kubectl label namespace haven-builds project=haven environment=${var.environment} --overwrite",
  ]

  depends_on = [rancher2_cluster_sync.cluster]
}

# --- 24. CNPG Cluster (haven_platform database) ---
# Applied after CNPG operator is ready. Uses base64-encoded manifest to avoid heredoc issues.
locals {
  cnpg_cluster_yaml = <<-YAML
    apiVersion: postgresql.cnpg.io/v1
    kind: Cluster
    metadata:
      name: haven-platform
      namespace: cnpg-system
    spec:
      instances: 1
      storage:
        storageClass: longhorn
        size: 20Gi
      bootstrap:
        initdb:
          database: haven_platform
          owner: haven_api
      affinity:
        tolerations:
          - operator: "Exists"
  YAML
}

resource "ssh_resource" "cnpg_cluster" {
  count       = var.enable_cnpg ? 1 : 0
  host        = module.hetzner_infra.management_ip
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "10m"

  commands = [
    "kubectl get secret -n fleet-default ${var.cluster_name}-kubeconfig -o jsonpath='{.data.value}' | base64 -d > /tmp/workload-kubeconfig",
    "echo '${base64encode(local.cnpg_cluster_yaml)}' | base64 -d | KUBECONFIG=/tmp/workload-kubeconfig kubectl apply -f -",
  ]

  depends_on = [rancher2_app_v2.cnpg]
}

# --- 25. Node Topology Labels (Haven Check #1: Multi-AZ) ---
# Labels nodes with topology.kubernetes.io/zone so Haven checker detects multi-AZ.
# The Haven infraMultiAZ check reads this label; without it all nodes appear in the same zone.
resource "ssh_resource" "node_topology_labels" {
  host        = module.hetzner_infra.management_ip
  user        = local.node_username
  private_key = tls_private_key.global_key.private_key_pem
  timeout     = "5m"

  commands = concat(
    # Get workload cluster kubeconfig via fleet-default secret
    ["kubectl get secret -n fleet-default ${var.cluster_name}-kubeconfig -o jsonpath='{.data.value}' | base64 -d > /tmp/workload-kubeconfig"],
    # Label master nodes with their zone
    [for i in range(var.master_count) :
      "KUBECONFIG=/tmp/workload-kubeconfig kubectl label node haven-master-${var.environment}-${i + 1} topology.kubernetes.io/zone=${local.master_locations[i]} topology.kubernetes.io/region=eu --overwrite"
    ],
    # Label worker nodes with their zone
    [for i in range(var.worker_count) :
      "KUBECONFIG=/tmp/workload-kubeconfig kubectl label node haven-worker-${var.environment}-${i + 1} topology.kubernetes.io/zone=${local.worker_locations[i]} topology.kubernetes.io/region=eu --overwrite"
    ]
  )

  depends_on = [rancher2_cluster_sync.cluster]
}
