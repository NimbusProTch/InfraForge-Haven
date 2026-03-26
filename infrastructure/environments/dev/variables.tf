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

variable "everest_operator_version" {
  description = "Percona Everest operator Helm chart version"
  type        = string
  default     = "1.4.0"
}

variable "everest_version" {
  description = "Percona Everest server Helm chart version"
  type        = string
  default     = "1.4.0"
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
