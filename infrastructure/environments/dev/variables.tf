# ===== Hetzner =====
variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "location_primary" {
  description = "Primary datacenter (Multi-AZ - Haven Check 1)"
  type        = string
  default     = "nbg1" # Nuremberg
}

variable "location_secondary" {
  description = "Secondary datacenter (Multi-AZ - Haven Check 1)"
  type        = string
  default     = "fsn1" # Falkenstein
}

# ===== Cluster Nodes =====
variable "master_server_type" {
  description = "RKE2 master node VM type"
  type        = string
  default     = "cpx32" # 4 vCPU, 8GB RAM
}

variable "worker_server_type" {
  description = "RKE2 worker node VM type"
  type        = string
  default     = "cpx42" # 8 vCPU, 16GB RAM
}

variable "master_count" {
  description = "Number of master nodes (Haven Check 2: min 3)"
  type        = number
  default     = 3
}

variable "worker_count" {
  description = "Number of worker nodes (Haven Check 2: min 3)"
  type        = number
  default     = 3
}

variable "os_image" {
  description = "Hetzner OS image"
  type        = string
  default     = "ubuntu-22.04"
}

# ===== Network =====
variable "network_cidr" {
  description = "Private network CIDR"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "Subnet CIDR"
  type        = string
  default     = "10.0.1.0/24"
}

# ===== RKE2 Cluster =====
variable "cluster_name" {
  description = "RKE2 cluster name"
  type        = string
  default     = "haven-dev"
}

variable "kubernetes_version" {
  description = "RKE2 Kubernetes version"
  type        = string
  default     = "v1.32.3+rke2r1"
}

# ===== Longhorn =====
variable "enable_longhorn" {
  description = "Enable Longhorn distributed storage (Haven Check 10)"
  type        = bool
  default     = true
}

variable "longhorn_version" {
  description = "Longhorn Helm chart version"
  type        = string
  default     = "1.7.1"
}

# ===== Cert-Manager =====
variable "enable_cert_manager" {
  description = "Enable Cert-Manager (Haven Check 12)"
  type        = bool
  default     = true
}

variable "cert_manager_version" {
  description = "Cert-Manager Helm chart version"
  type        = string
  default     = "v1.16.2"
}

# ===== Monitoring =====
variable "enable_monitoring" {
  description = "Enable kube-prometheus-stack (Haven Check 14)"
  type        = bool
  default     = true
}

variable "monitoring_version" {
  description = "kube-prometheus-stack Helm chart version"
  type        = string
  default     = "67.4.0"
}

# H1b-1 (P4.1): operator IP allow-list — passed through to hetzner-infra
# module for SSH 22, K8s API 6443, RKE2 supervisor 9345 firewall rules.
# Set this in terraform.tfvars to your VPN/office egress CIDRs. Defaults
# to "world open" temporarily so an unconfigured tofu apply doesn't lock
# the operator out, but the H1b-1 morning task is to set it explicitly.
variable "operator_cidrs" {
  description = "Allow-list CIDRs for SSH, K8s API, and RKE2 supervisor (port 9345). Set in tfvars."
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]
}

# H1b-1 (P4.1): hardcoded password default removed. The pre-fix value
# `"HavenAdmin2026!"` was committed to git history (still in older
# commits — rotate the actual password on the dev cluster as part of
# the H1b-1 morning task). The variable is now empty-default + mandatory
# in tfvars, matching the pattern of every other admin password in this
# file.
variable "grafana_admin_password" {
  description = "Grafana admin password — MUST be set via TF_VAR_grafana_admin_password or terraform.tfvars"
  type        = string
  sensitive   = true
  default     = ""
  validation {
    condition     = length(var.grafana_admin_password) >= 16 || var.grafana_admin_password == ""
    error_message = "grafana_admin_password must be at least 16 characters when set"
  }
}

# ===== Logging =====
variable "enable_logging" {
  description = "Enable Loki Stack (Haven Check 13)"
  type        = bool
  default     = true
}

variable "logging_version" {
  description = "Loki Stack Helm chart version"
  type        = string
  default     = "2.10.2"
}

# ===== Harbor =====
variable "enable_harbor" {
  description = "Enable Harbor image registry"
  type        = bool
  default     = true
}

variable "harbor_version" {
  description = "Harbor Helm chart version"
  type        = string
  default     = "1.16.2"
}

variable "harbor_admin_password" {
  description = "Harbor admin password"
  type        = string
  sensitive   = true
}

variable "harbor_registry_storage_size" {
  description = "Harbor registry PVC size"
  type        = string
  default     = "20Gi"
}

# ===== MinIO =====
variable "enable_minio" {
  description = "Enable MinIO object storage"
  type        = bool
  default     = true
}

variable "minio_version" {
  description = "MinIO Helm chart version"
  type        = string
  default     = "5.3.0"
}

variable "minio_root_user" {
  description = "MinIO root username"
  type        = string
  default     = "admin"
}

variable "minio_root_password" {
  description = "MinIO root password"
  type        = string
  sensitive   = true
}

variable "minio_storage_size" {
  description = "MinIO PVC size"
  type        = string
  default     = "20Gi"
}

# ===== H1e: MinIO Server-Side Encryption (SSE) =====
# Pre-fix MinIO had no encryption-at-rest config. Backup data (CNPG WAL,
# Loki chunks, Harbor blobs if MinIO was wired as the registry storage)
# was written to disk in plaintext. A Longhorn volume snapshot or a
# compromised node = plaintext recovery of every backup.
#
# Strategy (dev cluster, single-node MinIO): use MinIO's built-in
# `MINIO_KMS_SECRET_KEY` (a 32-byte symmetric key in base64) plus
# `MINIO_KMS_AUTO_ENCRYPTION=on` so every NEW write is transparently
# AES-256-GCM encrypted. Existing objects stay plaintext until rewritten;
# a separate migration script (`mc admin encrypt`) is needed to retro-fit
# the existing buckets.
#
# Production cluster should use Vault transit + MINIO_KMS_KES_* (HashiCorp
# KES sidecar) instead of a standalone KMS secret. Defer to a
# post-Vault-migration sprint.

variable "minio_kms_auto_encryption" {
  description = "Enable MinIO server-side auto-encryption for all new writes (AES-256-GCM via KMS_SECRET_KEY)"
  type        = bool
  default     = true
}

variable "minio_kms_secret_key" {
  description = <<-EOT
    MinIO KMS key in the format `<key-name>:<base64-32-bytes>`.

    Example value (DO NOT use this one in production — generate your own):

      haven-dev:6/MJP6sDywZxbcGOJjaH7N7l0sB+yVzqgzDzwK7Tx9w=

    To generate a fresh key:

      KEY=$(openssl rand 32 | base64)
      echo "haven-dev:$KEY"

    ## CRITICAL: back up the key BEFORE pasting into tfvars

    Losing this key = permanently losing every encrypted object. The key
    will live in two places:
      1. `terraform.tfvars` (gitignored, on the operator's machine)
      2. Tofu state backend (S3 / R2, encrypted at rest if SSE is on)

    Both copies can be lost (laptop dies + state corruption). BEFORE you
    paste the generated key into tfvars:

      a. Save it to a real password manager (1Password / Bitwarden)
         under "Haven dev MinIO KMS key"
      b. Verify you can read it back from the password manager
      c. THEN paste into tfvars and `tofu apply`

    Without step (a), an unrecoverable state corruption + a laptop loss
    is irrecoverable: every CNPG WAL backup, every Loki chunk, every
    encrypted Harbor blob is permanently unreadable.

    Set in `terraform.tfvars` (gitignored). Default empty string disables
    auto-encryption (the helm template skips the env var when blank).
    Once set, every NEW MinIO write is AES-256-GCM encrypted with this
    key.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}

# ===== ArgoCD =====
variable "enable_argocd" {
  description = "Enable ArgoCD GitOps"
  type        = bool
  default     = true
}

variable "argocd_version" {
  description = "ArgoCD Helm chart version"
  type        = string
  default     = "7.7.3"
}

# ===== Keycloak =====
variable "enable_keycloak" {
  description = "Enable Keycloak identity provider"
  type        = bool
  default     = true
}

variable "keycloak_chart_version" {
  description = "Keycloak Helm chart version (codecentric)"
  type        = string
  default     = "2.4.4"
}

variable "keycloak_admin_password" {
  description = "Keycloak admin password"
  type        = string
  sensitive   = true
}

# ===== Percona Everest =====
variable "enable_everest" {
  description = "Enable Percona Everest (PostgreSQL, MySQL, MongoDB)"
  type        = bool
  default     = true
}

variable "everest_version" {
  description = "Percona Everest Helm chart version"
  type        = string
  default     = "1.13.0"
}

# ===== Redis Operator =====
variable "enable_redis_operator" {
  description = "Enable OpsTree Redis Operator"
  type        = bool
  default     = true
}

variable "redis_operator_version" {
  description = "Redis Operator Helm chart version"
  type        = string
  default     = "0.18.0"
}

# ===== RabbitMQ Operator =====
variable "enable_rabbitmq_operator" {
  description = "Enable RabbitMQ Cluster Operator"
  type        = bool
  default     = true
}

variable "rabbitmq_operator_version" {
  description = "RabbitMQ Cluster Operator Helm chart version"
  type        = string
  default     = "4.3.26"
}

# ===== External-DNS =====
variable "enable_external_dns" {
  description = "Enable External-DNS (requires cloudflare_api_token)"
  type        = bool
  default     = false
}

variable "external_dns_version" {
  description = "External-DNS Helm chart version"
  type        = string
  default     = "1.15.0"
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "external_dns_domain_filters" {
  description = "Domain filters for External-DNS"
  type        = list(string)
  default     = []
}

variable "domain" {
  description = "Platform domain"
  type        = string
  default     = "haven.dev"
}

# ===== Encryption =====
variable "enable_wireguard_encryption" {
  description = <<-EOT
    Enable Cilium WireGuard pod-to-pod encryption.

    H1d (production-grade SaaS gap closure): default flipped to `true` on
    2026-04-09. Pre-fix the dev cluster ran with all pod-to-pod traffic in
    PLAINTEXT. On a shared node, a compromised pod could sniff every other
    tenant's traffic on the same host. WireGuard adds AEAD encryption at
    the Cilium datapath level, transparent to the workload.

    Requirements:
      - Kernel >= 5.6 (the dev cluster runs Ubuntu 22.04 / kernel 5.15 → OK)
      - `userspaceFallback: true` is set in the helm values for the rare
        case where a node lacks the kernel module — Cilium falls back to
        userspace WireGuard rather than failing closed.

    Trade-off:
      - CPU overhead ~10-20% per node depending on traffic volume
      - Latency +0.1-0.3 ms intra-cluster (negligible for HTTP/REST)
      - In our dev cluster (low traffic) the overhead is in the noise

    Activation requires `tofu apply` (Cilium HelmChartConfig is rewritten
    via the master cloud-init template). The change is rolling — Cilium
    pods restart node-by-node and re-establish encrypted tunnels.
    Existing flows are interrupted briefly during pod restart but
    application connections re-establish automatically.

    To disable for a particular environment (e.g. an extremely
    latency-sensitive prod that audits this differently): override to
    `false` in the env tfvars.
  EOT
  type        = bool
  default     = true
}

# ===== OIDC / Keycloak Integration =====
variable "enable_oidc" {
  description = "Enable Keycloak OIDC on kube-apiserver (IS4-01, requires Keycloak deployed)"
  type        = bool
  default     = false
}

variable "oidc_keycloak_realm" {
  description = "Keycloak realm name for OIDC"
  type        = string
  default     = "haven"
}

# ===== Gitea =====
variable "enable_gitea" {
  description = "Enable Gitea self-hosted git server (required for GitOps pipeline)"
  type        = bool
  default     = true
}

variable "gitea_version" {
  description = "Gitea Helm chart version"
  type        = string
  default     = "10.6.0"
}

variable "gitea_admin_user" {
  description = "Gitea admin username"
  type        = string
  default     = "gitea_admin"
}

variable "gitea_admin_password" {
  description = "Gitea admin password"
  type        = string
  sensitive   = true
}

variable "gitea_storage_size" {
  description = "Gitea data PVC size"
  type        = string
  default     = "10Gi"
}

# ===== Real Domain Mode =====
variable "use_real_domain" {
  description = "Switch hostnames from sslip.io pattern to real domain (IS5-02)"
  type        = bool
  default     = false
}

# ===== H1b-2 (P4.2): etcd snapshot + off-cluster S3 backend =====
# Pre-fix the dev cluster had ZERO automated etcd snapshots — total
# cluster loss = total data loss. Defaults take a daily local snapshot
# on each master at 02:00 UTC. Off-cluster upload requires explicit
# setup of an S3-compatible bucket (Cloudflare R2 free tier recommended).

variable "etcd_snapshot_schedule" {
  description = "Cron expression for automated etcd snapshots. Default: daily 02:00 UTC."
  type        = string
  default     = "0 2 * * *"
}

variable "etcd_snapshot_retention" {
  description = "Number of local etcd snapshots to retain on each master before pruning"
  type        = number
  default     = 30
}

variable "etcd_s3_enabled" {
  description = "Ship etcd snapshots to off-cluster S3-compatible bucket. Default false. Morning TODO: provision Cloudflare R2 (free 10 GB), set true, fill in keys."
  type        = bool
  default     = false
}

variable "etcd_s3_endpoint" {
  description = "S3-compatible endpoint URL (e.g. <account>.r2.cloudflarestorage.com)"
  type        = string
  default     = ""
}

variable "etcd_s3_bucket" {
  description = "S3 bucket name for etcd snapshots"
  type        = string
  default     = ""
}

variable "etcd_s3_folder" {
  description = "Subfolder inside the bucket (e.g. \"dev\")"
  type        = string
  default     = "dev"
}

variable "etcd_s3_region" {
  description = "S3 region (use \"auto\" for Cloudflare R2)"
  type        = string
  default     = "auto"
}

variable "etcd_s3_access_key" {
  description = "S3 access key — set via TF_VAR_etcd_s3_access_key or terraform.tfvars"
  type        = string
  default     = ""
  sensitive   = true
}

variable "etcd_s3_secret_key" {
  description = "S3 secret key — set via TF_VAR_etcd_s3_secret_key or terraform.tfvars"
  type        = string
  default     = ""
  sensitive   = true
}

# ===== H1a-2: kubectl OIDC integration via Keycloak =====
# Pre-fix the dev cluster had ZERO --oidc-* flags on kube-apiserver, so
# tenant admins could not use their Keycloak token with `kubectl`. After
# `tofu apply` (rolling master restart) + Keycloak realm reimport
# (`bootstrap-realm.sh --apply`), tenant admins get a token from the
# `haven-kubectl` public client and use it as a Bearer token with kubectl.

variable "keycloak_oidc_issuer_url" {
  description = "OIDC issuer URL for kube-apiserver token verification (no trailing slash). Must match the Keycloak `iss` claim."
  type        = string
  default     = "https://keycloak.46.225.42.2.sslip.io/realms/haven"
}

variable "keycloak_oidc_client_id" {
  description = "OIDC client_id used by kubectl. Must exist in haven realm as a public client (see keycloak/haven-realm.json)."
  type        = string
  default     = "haven-kubectl"
}
